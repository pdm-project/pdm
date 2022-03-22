from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Type, cast
from urllib.parse import urlparse

import tomlkit
from findpython import Finder

from pdm import termui
from pdm._types import Source
from pdm.exceptions import NoPythonVersion, PdmUsageError, ProjectError
from pdm.models import pip_shims
from pdm.models.caches import CandidateInfoCache, HashCache
from pdm.models.candidates import Candidate
from pdm.models.environment import Environment, GlobalEnvironment
from pdm.models.python import PythonInfo
from pdm.models.repositories import BaseRepository, LockedRepository, PyPIRepository
from pdm.models.requirements import Requirement, parse_requirement
from pdm.models.specifiers import PySpecSet, get_specifier
from pdm.project.config import Config
from pdm.project.metadata import MutableMetadata as Metadata
from pdm.utils import (
    atomic_open_for_write,
    cached_property,
    cd,
    expand_env_vars_in_auth,
    find_project_root,
    find_python_in_path,
    get_in_project_venv_python,
    get_venv_like_prefix,
    normalize_name,
)

if TYPE_CHECKING:
    from resolvelib.reporters import BaseReporter

    from pdm._vendor import halo
    from pdm.core import Core
    from pdm.resolver.providers import BaseProvider


PYENV_ROOT = os.path.expanduser(os.getenv("PYENV_ROOT", "~/.pyenv"))


class Project:
    """Core project class.

    Args:
        core: The core instance.
        root_path: The root path of the project.
        is_global: Whether the project is global.
        global_config: The path to the global config file.
    """

    PYPROJECT_FILENAME = "pyproject.toml"
    DEPENDENCIES_RE = re.compile(r"(?:(.+?)-)?dependencies")
    LOCKFILE_VERSION = "3.1"

    def __init__(
        self,
        core: Core,
        root_path: str | Path | None,
        is_global: bool = False,
        global_config: str | Path | None = None,
    ) -> None:
        self._pyproject: dict | None = None
        self._lockfile: dict | None = None
        self._environment: Environment | None = None
        self._python: PythonInfo | None = None
        self.core = core

        if global_config is None:
            global_config = Path.home() / ".pdm/config.toml"
        self.global_config = Config(Path(global_config), is_global=True)
        global_project = Path(self.global_config["global_project.path"])

        if root_path is None:
            root_path = (
                find_project_root(max_depth=self.global_config["project_max_depth"])
                if not is_global
                else global_project
            )
        if (
            not is_global
            and root_path is None
            and self.global_config["global_project.fallback"]
        ):
            self.core.ui.echo(
                "Project is not found, fallback to the global project",
                fg="yellow",
                err=True,
            )
            root_path = global_project
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
    def pyproject(self) -> dict | None:
        if not self._pyproject and self.pyproject_file.exists():
            data = tomlkit.parse(self.pyproject_file.read_text("utf-8"))
            self._pyproject = cast(dict, data)
        return self._pyproject

    @pyproject.setter
    def pyproject(self, data: dict[str, Any]) -> None:
        self._pyproject = data

    @property
    def tool_settings(self) -> dict:
        data = self.pyproject
        if not data:
            return {}
        return data.setdefault("tool", {}).setdefault("pdm", {})

    @property
    def lockfile(self) -> dict:
        if not self._lockfile:
            if not self.lockfile_file.is_file():
                raise ProjectError("Lock file does not exist.")
            data = tomlkit.parse(self.lockfile_file.read_text("utf-8"))
            self._lockfile = cast(dict, data)
        return self._lockfile

    @lockfile.setter
    def lockfile(self, data: dict[str, Any]) -> None:
        self._lockfile = data

    @property
    def config(self) -> dict[str, Any]:
        """A read-only dict configuration, any modifications won't land in the file."""
        result = dict(self.global_config)
        result.update(self.project_config)
        return result

    @property
    def scripts(self) -> dict[str, str | dict[str, str]]:
        return self.tool_settings.get("scripts", {})  # type: ignore

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
        self.project_config["python.path"] = value.path

    @property
    def python_executable(self) -> str:
        """For backward compatibility"""
        return str(self.python.executable)

    def resolve_interpreter(self) -> PythonInfo:
        """Get the Python interpreter path."""
        config = self.config
        if config.get("python.path") and not os.getenv("PDM_IGNORE_SAVED_PYTHON"):
            saved_path = config["python.path"]
            try:
                python = PythonInfo.from_path(saved_path)
                if self.python_requires.contains(str(python.version), True):
                    return python
            except (ValueError, FileNotFoundError):
                self.project_config.pop("python.path", None)
        if os.name == "nt":
            suffix = ".exe"
            scripts = "Scripts"
        else:
            suffix = ""
            scripts = "bin"

        # Resolve virtual environments from env-vars
        virtual_env = os.getenv("VIRTUAL_ENV", os.getenv("CONDA_PREFIX"))
        if config["python.use_venv"] and virtual_env:
            return PythonInfo.from_path(
                os.path.join(virtual_env, scripts, f"python{suffix}")
            )

        for py_version in self.find_interpreters():
            if self.python_requires.contains(str(py_version.version), True):
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
            env.python_requires = PySpecSet.equal_to(self.python.version)
            return env
        if self.config["python.use_venv"] and get_venv_like_prefix(
            self.python.executable
        ):
            # Only recognize venv created by python -m venv and virtualenv>20
            return GlobalEnvironment(self)
        return Environment(self)

    @property
    def environment(self) -> Environment:
        if not self._environment:
            self._environment = self.get_environment()
        return self._environment

    @environment.setter
    def environment(self, value: Environment) -> None:
        self._environment = value

    @property
    def python_requires(self) -> PySpecSet:
        return PySpecSet(self.meta.requires_python)

    def get_dependencies(self, group: str | None = None) -> dict[str, Requirement]:
        metadata = self.meta
        optional_dependencies = metadata.get("optional-dependencies", {})
        dev_dependencies = self.tool_settings.get("dev-dependencies", {})
        if group in (None, "default"):
            deps = metadata.get("dependencies", [])
        else:
            if group in optional_dependencies and group in dev_dependencies:
                self.core.ui.echo(
                    f"The {group} group exists in both [optional-dependencies] "
                    "and [dev-dependencies], the former is taken.",
                    err=True,
                    fg="yellow",
                )
            if group in optional_dependencies:
                deps = optional_dependencies[group]
            elif group in dev_dependencies:
                deps = dev_dependencies[group]
            else:
                raise PdmUsageError(f"Non-exist group {group}")
        result = {}
        with cd(self.root):
            for line in deps:
                if line.startswith("-e "):
                    req = parse_requirement(line[3:].strip(), True)
                else:
                    req = parse_requirement(line)
                # make editable packages behind normal ones to override correctly.
                result[req.identify()] = req
        return result

    @property
    def dependencies(self) -> dict[str, Requirement]:
        return self.get_dependencies()

    @property
    def dev_dependencies(self) -> dict[str, Requirement]:
        """All development dependencies"""
        dev_group = self.tool_settings.get("dev-dependencies", {})
        if not dev_group:
            return {}
        result = {}
        with cd(self.root):
            for _, deps in dev_group.items():
                for line in deps:
                    if line.startswith("-e "):
                        req = parse_requirement(line[3:].strip(), True)
                    else:
                        req = parse_requirement(line)
                    result[req.identify()] = req
        return result

    def iter_groups(self) -> Iterable[str]:
        groups = {"default"}
        if self.meta.optional_dependencies:
            groups.update(self.meta.optional_dependencies.keys())
        if self.tool_settings.get("dev-dependencies"):
            groups.update(self.tool_settings["dev-dependencies"].keys())
        return groups

    @property
    def all_dependencies(self) -> dict[str, dict[str, Requirement]]:
        return {group: self.get_dependencies(group) for group in self.iter_groups()}

    @property
    def allow_prereleases(self) -> bool | None:
        return self.tool_settings.get("allow_prereleases")

    @property
    def sources(self) -> list[Source]:
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
        expanded_sources: list[Source] = [
            Source(
                url=expand_env_vars_in_auth(s["url"]),
                verify_ssl=s.get("verify_ssl", True),
                name=s.get("name", urlparse(s["url"]).hostname),
                type=s.get("type", "index"),
            )
            for s in sources
        ]
        return expanded_sources

    def get_repository(self, cls: Type[BaseRepository] | None = None) -> BaseRepository:
        """Get the repository object"""
        if cls is None:
            cls = PyPIRepository
        sources = self.sources or []
        return cls(sources, self.environment)

    @property
    def locked_repository(self) -> LockedRepository:
        import copy

        try:
            lockfile = copy.deepcopy(self.lockfile)
        except ProjectError:
            lockfile = {}

        return LockedRepository(lockfile, self.sources, self.environment)

    def get_provider(
        self,
        strategy: str = "all",
        tracked_names: Iterable[str] | None = None,
        for_install: bool = False,
    ) -> BaseProvider:
        """Build a provider class for resolver.

        :param strategy: the resolve strategy
        :param tracked_names: the names of packages that needs to update
        :param for_install: if the provider is for install
        :returns: The provider object
        """

        from pdm.resolver.providers import (
            BaseProvider,
            EagerUpdateProvider,
            ReusePinProvider,
        )

        repository = self.get_repository(cls=self.core.repository_class)
        allow_prereleases = self.allow_prereleases
        overrides = {
            normalize_name(k): v
            for k, v in self.tool_settings.get("overrides", {}).items()
        }
        if strategy != "all" and not self.is_lockfile_compatible():
            self.core.ui.echo(
                "Updating the whole lock file as it is not compatible with PDM",
                fg="yellow",
                err=True,
            )
            strategy = "all"
        if not for_install and strategy == "all":
            return BaseProvider(repository, allow_prereleases, overrides)

        locked_repository = self.locked_repository
        if for_install:
            return BaseProvider(locked_repository, allow_prereleases, overrides)
        provider_class = (
            ReusePinProvider if strategy == "reuse" else EagerUpdateProvider
        )
        return provider_class(
            locked_repository.all_candidates,
            tracked_names or (),
            repository,
            allow_prereleases,
            overrides,
        )

    def get_reporter(
        self,
        requirements: list[Requirement],
        tracked_names: Iterable[str] | None = None,
        spinner: halo.Halo | termui.DummySpinner | None = None,
    ) -> BaseReporter:
        """Return the reporter object to construct a resolver.

        :param requirements: requirements to resolve
        :param tracked_names: the names of packages that needs to update
        :param spinner: optional spinner object
        :returns: a reporter
        """
        from pdm.resolver.reporters import SpinnerReporter

        return SpinnerReporter(spinner or termui.DummySpinner(), requirements)

    def get_lock_metadata(self) -> dict[str, Any]:
        content_hash = tomlkit.string("sha256:" + self.get_content_hash("sha256"))
        content_hash.trivia.trail = "\n\n"
        return {"lock_version": self.LOCKFILE_VERSION, "content_hash": content_hash}

    def write_lockfile(
        self, toml_data: dict, show_message: bool = True, write: bool = True
    ) -> None:
        toml_data["metadata"].update(self.get_lock_metadata())

        if write:
            with atomic_open_for_write(self.lockfile_file) as fp:
                tomlkit.dump(toml_data, fp)  # type: ignore
            if show_message:
                self.core.ui.echo(f"Changes are written to {termui.green('pdm.lock')}.")
            self._lockfile = None
        else:
            self._lockfile = toml_data

    def make_self_candidate(self, editable: bool = True) -> Candidate:
        req = parse_requirement(pip_shims.path_to_url(self.root.as_posix()), editable)
        req.name = self.meta.name
        return Candidate(req, name=self.meta.name, version=self.meta.version)

    def get_content_hash(self, algo: str = "md5") -> str:
        # Only calculate sources and dependencies groups. Otherwise lock file is
        # considered as unchanged.
        dump_data = {
            "sources": self.tool_settings.get("source", []),
            "dependencies": self.meta.get("dependencies", []),
            "dev-dependencies": self.tool_settings.get("dev-dependencies", {}),
            "optional-dependencies": self.meta.get("optional-dependencies", {}),
            "requires-python": self.meta.get("requires-python", ""),
            "overrides": self.tool_settings.get("overrides", {}),
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

    def is_lockfile_compatible(self) -> bool:
        if not self.lockfile_file.exists():
            return True
        lockfile_version = str(
            self.lockfile.get("metadata", {}).get("lock_version", "")
        )
        if not lockfile_version:
            return False
        if "." not in lockfile_version:
            lockfile_version += ".0"
        accepted = get_specifier(f"~={lockfile_version}")
        return accepted.contains(self.LOCKFILE_VERSION)

    def get_pyproject_dependencies(self, group: str, dev: bool = False) -> list[str]:
        """Get the dependencies array in the pyproject.toml"""
        if group == "default":
            return self.meta.setdefault("dependencies", [])
        else:
            deps_dict = {
                False: self.meta.setdefault("optional-dependencies", {}),
                True: self.tool_settings.setdefault("dev-dependencies", {}),
            }
            for deps in deps_dict.values():
                if group in deps:
                    return deps[group]
            return deps_dict[dev].setdefault(group, [])

    def add_dependencies(
        self,
        requirements: dict[str, Requirement],
        to_group: str = "default",
        dev: bool = False,
        show_message: bool = True,
    ) -> None:
        deps = self.get_pyproject_dependencies(to_group, dev).multiline(  # type: ignore
            True
        )
        for _, dep in requirements.items():
            matched_index = next(
                (i for i, r in enumerate(deps) if dep.matches(r)), None
            )
            if matched_index is None:
                deps.append(dep.as_line())
            else:
                req = dep.as_line()
                deps[matched_index] = req
        self.write_pyproject(show_message)

    def write_pyproject(self, show_message: bool = True) -> None:
        with atomic_open_for_write(
            self.pyproject_file.as_posix(), encoding="utf-8"
        ) as f:
            tomlkit.dump(self.pyproject, f)  # type: ignore
        if show_message:
            self.core.ui.echo(
                f"Changes are written to {termui.green('pyproject.toml')}."
            )
        self._pyproject = None

    @property
    def meta(self) -> Metadata:
        if not self.pyproject:
            self.pyproject = {"project": tomlkit.table()}
        m = Metadata(self.pyproject_file, False)
        m._metadata = self.pyproject.get("project", {})
        m._tool_settings = self.tool_settings
        return m

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
        return Path(self.config.get("cache_dir", ""))

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

    def find_interpreters(self, python_spec: str | None = None) -> Iterable[PythonInfo]:
        """Return an iterable of interpreter paths that matches the given specifier,
        which can be:
            1. a version specifier like 3.7
            2. an absolute path
            3. a short name like python3
            4. None that returns all possible interpreters
        """
        config = self.config
        python: str | Path | None = None

        if not python_spec:
            if config.get("python.use_pyenv", True) and os.path.exists(PYENV_ROOT):
                pyenv_shim = os.path.join(PYENV_ROOT, "shims", "python3")
                if os.name == "nt":
                    pyenv_shim += ".bat"
                if os.path.exists(pyenv_shim):
                    yield PythonInfo.from_path(pyenv_shim)
                elif os.path.exists(pyenv_shim.replace("python3", "python")):
                    yield PythonInfo.from_path(pyenv_shim.replace("python3", "python"))
            if config.get("python.use_venv"):
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
        finder = Finder(resolve_symlinks=True)
        for entry in finder.find_all(*args):
            yield PythonInfo(entry)
        if not python_spec:
            this_python = getattr(sys, "_base_executable", sys.executable)
            yield PythonInfo.from_path(this_python)
