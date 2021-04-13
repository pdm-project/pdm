from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Type, Union

import tomlkit
from pythonfinder import Finder
from pythonfinder.environment import PYENV_INSTALLED, PYENV_ROOT
from tomlkit.items import Comment, Whitespace

from pdm import termui
from pdm._types import Source
from pdm.exceptions import NoPythonVersion, PdmUsageError, ProjectError
from pdm.models import pip_shims
from pdm.models.caches import CandidateInfoCache, HashCache
from pdm.models.candidates import Candidate
from pdm.models.environment import Environment, GlobalEnvironment
from pdm.models.python import PythonInfo
from pdm.models.repositories import BaseRepository, PyPIRepository
from pdm.models.requirements import Requirement, parse_requirement
from pdm.models.specifiers import PySpecSet
from pdm.project.config import Config
from pdm.project.metadata import MutableMetadata as Metadata
from pdm.utils import (
    atomic_open_for_write,
    cached_property,
    cd,
    find_project_root,
    find_python_in_path,
    get_in_project_venv_python,
    is_venv_python,
    setdefault,
)

if TYPE_CHECKING:
    from resolvelib.reporters import BaseReporter

    from pdm._vendor import halo
    from pdm.core import Core
    from pdm.resolver.providers import BaseProvider


class Project:
    """Core project class"""

    PYPROJECT_FILENAME = "pyproject.toml"
    DEPENDENCIES_RE = re.compile(r"(?:(.+?)-)?dependencies")
    PYPROJECT_VERSION = "2"
    GLOBAL_PROJECT = Path.home() / ".pdm" / "global-project"

    def __init__(
        self, core: Core, root_path: Optional[os.PathLike], is_global: bool = False
    ) -> None:
        self._pyproject: Optional[Dict] = None
        self._lockfile: Optional[Dict] = None
        self._environment: Optional[Environment] = None
        self._python: Optional[PythonInfo] = None
        self.core = core

        if root_path is None:
            root_path = find_project_root() if not is_global else self.GLOBAL_PROJECT
        if not is_global and root_path is None and self.global_config["auto_global"]:
            self.core.ui.echo(
                "Project is not found, fallback to the global project",
                fg="yellow",
                err=True,
            )
            root_path = self.GLOBAL_PROJECT
            is_global = True

        self.root = Path(root_path or "").absolute()
        self.is_global = is_global
        self.init_global_project()

    def __repr__(self) -> str:
        return f"<Project '{self.root.as_posix()}'>"

    @property
    def pyproject_file(self) -> Path:
        return self.root / self.PYPROJECT_FILENAME

    @property
    def lockfile_file(self) -> Path:
        return self.root / "pdm.lock"

    @property
    def pyproject(self) -> Optional[dict]:
        if not self._pyproject and self.pyproject_file.exists():
            data = tomlkit.parse(self.pyproject_file.read_text("utf-8"))
            self._pyproject = data
        return self._pyproject

    @pyproject.setter
    def pyproject(self, data: Dict[str, Any]) -> None:
        self._pyproject = data

    @property
    def tool_settings(self) -> dict:
        data = self.pyproject
        if not data:
            return {}
        return setdefault(setdefault(data, "tool", {}), "pdm", {})

    @property
    def lockfile(self) -> dict:
        if not self._lockfile:
            if not self.lockfile_file.is_file():
                raise ProjectError("Lock file does not exist.")
            data = tomlkit.parse(self.lockfile_file.read_text("utf-8"))
            self._lockfile = data
        return self._lockfile

    @lockfile.setter
    def lockfile(self, data: Dict[str, Any]) -> None:
        self._lockfile = data

    @property
    def config(self) -> Dict[str, Any]:
        """A read-only dict configuration, any modifications won't land in the file."""
        result = dict(self.global_config)
        result.update(self.project_config)
        return result

    @property
    def scripts(self) -> Dict[str, Union[str, Dict[str, str]]]:
        return self.tool_settings.get("scripts")

    @cached_property
    def global_config(self) -> Config:
        """Read-and-writable configuration dict for global settings"""
        return Config(Path.home() / ".pdm" / "config.toml", is_global=True)

    @cached_property
    def project_config(self) -> Config:
        """Read-and-writable configuration dict for project settings"""
        return Config(self.root / ".pdm.toml")

    @property
    def python(self) -> PythonInfo:
        if not self._python:
            self._python = self.resolve_interpreter()
        return self._python

    @python.setter
    def python(self, value: PythonInfo) -> None:
        self._python = value
        self.project_config["python.path"] = value.executable

    @property
    def python_executable(self) -> str:
        """For backward compatibility"""
        return self.python.executable

    def resolve_interpreter(self) -> PythonInfo:
        """Get the Python interpreter path."""
        config = self.config
        if self.project_config.get("python.path") and not os.getenv(
            "PDM_IGNORE_SAVED_PYTHON"
        ):
            saved_path = self.project_config["python.path"]
            try:
                return PythonInfo.from_path(saved_path)
            except (ValueError, FileNotFoundError):
                del self.project_config["python.path"]
        if os.name == "nt":
            suffix = ".exe"
            scripts = "Scripts"
        else:
            suffix = ""
            scripts = "bin"
        virtual_env = os.getenv("VIRTUAL_ENV")
        if config["use_venv"] and virtual_env:
            return PythonInfo.from_path(
                os.path.join(virtual_env, scripts, f"python{suffix}")
            )

        for py_version in self.find_interpreters():
            if self.python_requires.contains(str(py_version.version)):
                self.python = py_version
                return py_version

        raise NoPythonVersion(
            "No Python that satisfies {} is found on the system.".format(
                self.python_requires
            )
        )

    def get_environment(self) -> Environment:
        """Get the environment selected by this project"""
        if self.is_global:
            env = GlobalEnvironment(self)
            # Rewrite global project's python requires to be
            # compatible with the exact version
            env.python_requires = PySpecSet(f"=={self.python.version}")
            return env
        if self.config["use_venv"] and is_venv_python(self.python.executable):
            # Only recognize venv created by python -m venv and virtualenv>20
            return GlobalEnvironment(self)
        return Environment(self)

    @property
    def environment(self) -> Environment:
        if not self._environment:
            self._environment = self.get_environment()
        return self._environment

    @property
    def python_requires(self) -> PySpecSet:
        return PySpecSet(self.meta.requires_python)

    def get_dependencies(self, section: Optional[str] = None) -> Dict[str, Requirement]:
        metadata = self.meta
        optional_dependencies = metadata.get("optional-dependencies", {})
        dev_dependencies = self.tool_settings.get("dev-dependencies", {})
        if section in (None, "default"):
            deps = metadata.get("dependencies", [])
        else:
            if section in optional_dependencies and section in dev_dependencies:
                self.core.ui.echo(
                    f"The {section} section exists in both [optional-dependencies] "
                    "and [dev-dependencies], the former is taken.",
                    err=True,
                    fg="yellow",
                )
            if section in optional_dependencies:
                deps = optional_dependencies[section]
            elif section in dev_dependencies:
                deps = dev_dependencies[section]
            else:
                raise PdmUsageError(f"Non-exist section {section}")
        result = {}
        with cd(self.root):
            for line in deps:
                if line.startswith("-e "):
                    req = parse_requirement(line[3:].strip(), True)
                else:
                    req = parse_requirement(line)
                req.from_section = section or "default"
                # make editable packages behind normal ones to override correctly.
                result[req.identify()] = req
        return result

    @property
    def dependencies(self) -> Dict[str, Requirement]:
        return self.get_dependencies()

    @property
    def dev_dependencies(self) -> Dict[str, Requirement]:
        """All development dependencies"""
        dev_group = self.tool_settings.get("dev-dependencies", {})
        if not dev_group:
            return {}
        result = {}
        with cd(self.root):
            for section, deps in dev_group.items():
                for line in deps:
                    if line.startswith("-e "):
                        req = parse_requirement(line[3:].strip(), True)
                    else:
                        req = parse_requirement(line)
                    req.from_section = section
                    result[req.identify()] = req
        return result

    def iter_sections(self) -> Iterable[str]:
        result = {"default"}
        if self.meta.optional_dependencies:
            result.update(self.meta.optional_dependencies.keys())
        if self.tool_settings.get("dev-dependencies"):
            result.update(self.tool_settings["dev-dependencies"].keys())
        return result

    @property
    def all_dependencies(self) -> Dict[str, Dict[str, Requirement]]:
        return {
            section: self.get_dependencies(section) for section in self.iter_sections()
        }

    @property
    def allow_prereleases(self) -> Optional[bool]:
        return self.tool_settings.get("allow_prereleases")

    @property
    def sources(self) -> List[Source]:
        sources = list(self.tool_settings.get("source", []))
        if all(source.get("name") != "pypi" for source in sources):
            sources.insert(
                0,
                {
                    "url": self.config["pypi.url"],
                    "verify_ssl": self.config["pypi.verify_ssl"],
                    "name": "pypi",
                },
            )
        return sources

    def get_repository(
        self, cls: Optional[Type[BaseRepository]] = None
    ) -> BaseRepository:
        """Get the repository object"""
        if cls is None:
            cls = PyPIRepository
        sources = self.sources or []
        return cls(sources, self.environment)

    def get_provider(
        self,
        strategy: str = "all",
        tracked_names: Optional[Iterable[str]] = None,
    ) -> BaseProvider:
        """Build a provider class for resolver.

        :param strategy: the resolve strategy
        :param tracked_names: the names of packages that needs to update
        :returns: The provider object
        """
        from pdm.resolver.providers import (
            BaseProvider,
            EagerUpdateProvider,
            ReusePinProvider,
        )

        repository = self.get_repository(cls=self.core.repository_class)
        allow_prereleases = self.allow_prereleases
        requires_python = self.environment.python_requires
        if strategy == "all":
            return BaseProvider(repository, requires_python, allow_prereleases)
        provider_class = (
            ReusePinProvider if strategy == "reuse" else EagerUpdateProvider
        )
        preferred_pins = self.get_locked_candidates("__all__")
        return provider_class(
            preferred_pins,
            tracked_names or (),
            repository,
            requires_python,
            allow_prereleases,
        )

    def get_reporter(
        self,
        requirements: List[Requirement],
        tracked_names: Optional[Iterable[str]] = None,
        spinner: Optional[halo.Halo] = None,
    ) -> BaseReporter:
        """Return the reporter object to construct a resolver.

        :param requirements: requirements to resolve
        :param tracked_names: the names of packages that needs to update
        :param spinner: optional spinner object
        :returns: a reporter
        """
        from pdm.resolver.reporters import SpinnerReporter

        return SpinnerReporter(spinner, requirements)

    def get_lock_metadata(self) -> Dict[str, Any]:
        content_hash = tomlkit.string("sha256:" + self.get_content_hash("sha256"))
        content_hash.trivia.trail = "\n\n"
        return {"lock_version": self.PYPROJECT_VERSION, "content_hash": content_hash}

    def write_lockfile(self, toml_data: Dict, show_message: bool = True) -> None:
        toml_data["metadata"].update(self.get_lock_metadata())

        with atomic_open_for_write(self.lockfile_file) as fp:
            fp.write(tomlkit.dumps(toml_data))
        if show_message:
            self.core.ui.echo(f"Changes are written to {termui.green('pdm.lock')}.")
        self._lockfile = None

    def make_self_candidate(self, editable: bool = True) -> Candidate:
        req = parse_requirement(pip_shims.path_to_url(self.root.as_posix()), editable)
        req.name = self.meta.name
        return Candidate(
            req, self.environment, name=self.meta.name, version=self.meta.version
        )

    def get_locked_candidates(
        self, section: Optional[str] = None
    ) -> Dict[str, Candidate]:
        if not self.lockfile_file.is_file():
            return {}
        section = section or "default"
        result = {}
        for package in [dict(p) for p in self.lockfile.get("package", [])]:
            if section != "__all__" and section not in package["sections"]:
                continue
            version = package.get("version")
            if version:
                package["version"] = f"=={version}"
            package_name = package.pop("name")
            req = Requirement.from_req_dict(package_name, dict(package))
            can = Candidate(req, self.environment, name=package_name, version=version)
            can.sections = package.get("sections", [])
            can.marker = req.marker
            can.hashes = {
                item["file"]: item["hash"]
                for item in self.lockfile["metadata"]
                .get("files", {})
                .get(f"{req.key} {version}", [])
            } or None
            result[req.identify()] = can
        if section in ("default", "__all__") and self.meta.name and self.meta.version:
            result[self.meta.project_name.lower()] = self.make_self_candidate(True)
        return result

    def get_content_hash(self, algo: str = "md5") -> str:
        # Only calculate sources and dependencies sections. Otherwise lock file is
        # considered as unchanged.
        dump_data = {
            "sources": self.tool_settings.get("source", []),
            "dependencies": self.meta.get("dependencies", []),
            "dev-dependencies": self.tool_settings.get("dev-dependencies", {}),
            "optional-dependencies": self.meta.get("optional-dependencies", {}),
            "requires-python": self.meta.get("requires-python", ""),
        }
        pyproject_content = json.dumps(dump_data, sort_keys=True)
        hasher = hashlib.new(algo)
        hasher.update(pyproject_content.encode("utf-8"))
        return hasher.hexdigest()

    def is_lockfile_hash_match(self) -> bool:
        if not self.lockfile_file.exists():
            return False
        hash_in_lockfile = str(
            self.lockfile.get("metadata", {}).get("content_hash", "")
        )
        if not hash_in_lockfile:
            return False
        algo, hash_value = hash_in_lockfile.split(":")
        content_hash = self.get_content_hash(algo)
        return content_hash == hash_value

    def get_pyproject_dependencies(self, section: str, dev: bool = False) -> List[str]:
        """Get the dependencies array in the pyproject.toml"""
        if section == "default":
            return setdefault(self.meta, "dependencies", [])
        elif dev:
            return setdefault(
                setdefault(self.tool_settings, "dev-dependencies", {}), section, []
            )
        else:
            return setdefault(
                setdefault(self.meta, "optional-dependencies", {}), section, []
            )

    def add_dependencies(
        self,
        requirements: Dict[str, Requirement],
        to_section: str = "default",
        dev: bool = False,
        show_message: bool = True,
    ) -> None:
        deps = self.get_pyproject_dependencies(to_section, dev)
        for _, dep in requirements.items():
            matched_index = next(
                (i for i, r in enumerate(deps) if dep.matches(r)), None
            )
            if matched_index is None:
                deps.append(dep.as_line())
            else:
                req = dep.as_line()
                deps[matched_index] = req
                # XXX: This dirty part is for tomlkit.Array.__setitem__()
                j = 0
                for i in range(len(deps._value)):
                    if isinstance(deps._value[i], (Comment, Whitespace)):
                        continue
                    if j == matched_index:
                        deps._value[i] = tomlkit.item(req)
                        break
                    j += 1
            deps.multiline(True)
        self.write_pyproject(show_message)

    def write_pyproject(self, show_message: bool = True) -> None:
        with atomic_open_for_write(
            self.pyproject_file.as_posix(), encoding="utf-8"
        ) as f:
            f.write(tomlkit.dumps(self.pyproject))
        if show_message:
            self.core.ui.echo(
                f"Changes are written to {termui.green('pyproject.toml')}."
            )
        self._pyproject = None

    @property
    def meta(self) -> Metadata:
        if not self.pyproject:
            self.pyproject = {"project": tomlkit.table()}
        return Metadata(self.pyproject_file, self.pyproject.get("project", {}))

    def init_global_project(self) -> None:
        if not self.is_global:
            return
        if not self.pyproject_file.exists():
            self.root.mkdir(parents=True, exist_ok=True)
            self.pyproject_file.write_text(
                """\
[project]
dependencies = ["pip", "setuptools", "wheel"]
"""
            )
            self._pyproject = None

    @property
    def cache_dir(self) -> Path:
        return Path(self.config.get("cache_dir"))

    def cache(self, name: str) -> Path:
        path = self.cache_dir / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def make_wheel_cache(self) -> pip_shims.WheelCache:
        return pip_shims.WheelCache(
            self.cache_dir.as_posix(), pip_shims.FormatControl(set(), set())
        )

    def make_candidate_info_cache(self) -> CandidateInfoCache:

        python_hash = hashlib.sha1(
            str(self.environment.python_requires).encode()
        ).hexdigest()
        file_name = f"package_meta_{python_hash}.json"
        return CandidateInfoCache(self.cache("metadata") / file_name)

    def make_hash_cache(self) -> HashCache:
        return HashCache(directory=self.cache("hashes").as_posix())

    def find_interpreters(
        self, python_spec: Optional[str] = None
    ) -> Iterable[PythonInfo]:
        """Return an iterable of interpreter paths that matches the given specifier,
        which can be:
            1. a version specifier like 3.7
            2. an absolute path
            3. a short name like python3
            4. None that returns all possible interpreters
        """
        config = self.config
        python: Optional[os.PathLike] = None

        if not python_spec:
            if config.get("python.use_pyenv", True) and PYENV_INSTALLED:
                yield PythonInfo.from_path(os.path.join(PYENV_ROOT, "shims", "python"))
            if config.get("use_venv"):
                python = get_in_project_venv_python(self.root)
                if python:
                    yield PythonInfo.from_path(python)
            python = shutil.which("python")
            if python:
                yield PythonInfo.from_path(python)
            args = []
        else:
            if not all(c.isdigit() for c in python_spec.split(".")):
                if Path(python_spec).exists():
                    python = find_python_in_path(python_spec)
                    if python:
                        yield PythonInfo.from_path(python)
                else:
                    python = shutil.which(python_spec)
                    if python:
                        yield PythonInfo.from_path(python)
                return
            args = [int(v) for v in python_spec.split(".") if v != ""]
        finder = Finder()
        for entry in finder.find_all_python_versions(*args):
            yield PythonInfo.from_python_version(entry.py_version)
        if not python_spec:
            this_python = getattr(sys, "_base_executable", sys.executable)
            yield PythonInfo.from_path(this_python)
