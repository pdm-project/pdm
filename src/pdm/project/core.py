from __future__ import annotations

import contextlib
import hashlib
import os
import re
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, cast

import platformdirs
import tomlkit
from findpython import Finder
from tomlkit.items import Array
from unearth import Link

from pdm import termui
from pdm._types import RepositoryConfig
from pdm.compat import cached_property
from pdm.environments import BaseEnvironment, PythonEnvironment, PythonLocalEnvironment
from pdm.exceptions import NoPythonVersion, PdmUsageError, ProjectError
from pdm.models.backends import BuildBackend, get_backend_by_spec
from pdm.models.caches import CandidateInfoCache, HashCache, WheelCache
from pdm.models.candidates import Candidate, make_candidate
from pdm.models.python import PythonInfo
from pdm.models.repositories import BaseRepository, LockedRepository
from pdm.models.requirements import Requirement, parse_requirement, strip_extras
from pdm.models.specifiers import PySpecSet, get_specifier
from pdm.project.config import Config
from pdm.project.lockfile import Lockfile
from pdm.project.project_file import PyProject
from pdm.utils import (
    cd,
    deprecation_warning,
    expand_env_vars_in_auth,
    find_project_root,
    find_python_in_path,
    normalize_name,
    path_to_url,
)

if TYPE_CHECKING:
    from resolvelib.reporters import BaseReporter

    from pdm._types import Spinner
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
    LOCKFILE_FILENAME = "pdm.lock"
    DEPENDENCIES_RE = re.compile(r"(?:(.+?)-)?dependencies")

    def __init__(
        self,
        core: Core,
        root_path: str | Path | None,
        is_global: bool = False,
        global_config: str | Path | None = None,
    ) -> None:
        self._lockfile: Lockfile | None = None
        self._environment: BaseEnvironment | None = None
        self._python: PythonInfo | None = None
        self.core = core

        if global_config is None:
            global_config = platformdirs.user_config_path("pdm") / "config.toml"
        self.global_config = Config(Path(global_config), is_global=True)
        global_project = Path(self.global_config["global_project.path"])

        if root_path is None:
            root_path = (
                find_project_root(max_depth=self.global_config["project_max_depth"])
                if not is_global
                else global_project
            )
        if not is_global and root_path is None and self.global_config["global_project.fallback"]:
            root_path = global_project
            is_global = True
            if self.global_config["global_project.fallback_verbose"]:
                self.core.ui.echo(
                    "Project is not found, fallback to the global project",
                    style="warning",
                    err=True,
                )

        self.root: Path = Path(root_path or "").absolute()
        self.is_global = is_global
        self.init_global_project()

    def __repr__(self) -> str:
        return f"<Project '{self.root.as_posix()}'>"

    @cached_property
    def pyproject(self) -> PyProject:
        return PyProject(self.root / self.PYPROJECT_FILENAME, ui=self.core.ui)

    @property
    def lockfile(self) -> Lockfile:
        if self._lockfile is None:
            self._lockfile = Lockfile(self.root / self.LOCKFILE_FILENAME, ui=self.core.ui)
        return self._lockfile

    def set_lockfile(self, path: str | Path) -> None:
        self._lockfile = Lockfile(path, ui=self.core.ui)

    @property
    def config(self) -> dict[str, Any]:
        """A read-only dict configuration, any modifications won't land in the file."""
        result = dict(self.global_config)
        result.update(self.project_config)
        return result

    @property
    def scripts(self) -> dict[str, str | dict[str, str]]:
        return self.pyproject.settings.get("scripts", {})

    @cached_property
    def project_config(self) -> Config:
        """Read-and-writable configuration dict for project settings"""
        config = Config(self.root / "pdm.toml")
        # TODO: for backward compatibility, remove this in the future
        if self.root.joinpath(".pdm.toml").exists():
            legacy_config = Config(self.root / ".pdm.toml").self_data
            config.update((k, v) for k, v in legacy_config.items() if k != "python.path")
        return config

    @property
    def name(self) -> str | None:
        return self.pyproject.metadata.get("name")

    @property
    def python(self) -> PythonInfo:
        if not self._python:
            self._python = self.resolve_interpreter()
            if self._python.major < 3:
                raise PdmUsageError(
                    "Python 2.7 has reached EOL and PDM no longer supports it. "
                    "Please upgrade your Python to 3.6 or later.",
                )
        return self._python

    @python.setter
    def python(self, value: PythonInfo) -> None:
        self._python = value
        self._saved_python = value.path.as_posix()

    @property
    def _saved_python(self) -> str | None:
        if os.getenv("PDM_PYTHON"):
            return os.getenv("PDM_PYTHON")
        with contextlib.suppress(FileNotFoundError):
            return self.root.joinpath(".pdm-python").read_text("utf-8").strip()
        with contextlib.suppress(FileNotFoundError):
            # TODO: remove this in the future
            with self.root.joinpath(".pdm.toml").open("rb") as fp:
                data = tomlkit.load(fp)
                if data.get("python", {}).get("path"):
                    return data["python"]["path"]
        return None

    @_saved_python.setter
    def _saved_python(self, value: str | None) -> None:
        python_file = self.root.joinpath(".pdm-python")
        if value is None:
            with contextlib.suppress(FileNotFoundError):
                python_file.unlink()
            return
        python_file.write_text(value, "utf-8")

    def resolve_interpreter(self) -> PythonInfo:
        """Get the Python interpreter path."""
        from pdm.cli.commands.venv.utils import get_venv_python, iter_venvs

        def match_version(python: PythonInfo) -> bool:
            return python.valid and self.python_requires.contains(python.version, True)

        def note(message: str) -> None:
            if not self.is_global:
                self.core.ui.echo(message, style="warning", err=True)

        config = self.config
        saved_path = self._saved_python
        if saved_path and not os.getenv("PDM_IGNORE_SAVED_PYTHON"):
            python = PythonInfo.from_path(saved_path)
            if match_version(python):
                return python
            self._saved_python = None  # Clear the saved path if it doesn't match

        if config.get("python.use_venv") and not self.is_global and not os.getenv("PDM_IGNORE_ACTIVE_VENV"):
            # Resolve virtual environments from env-vars
            venv_in_env = os.getenv("VIRTUAL_ENV", os.getenv("CONDA_PREFIX"))
            if venv_in_env:
                python = PythonInfo.from_path(get_venv_python(Path(venv_in_env)))
                if match_version(python):
                    note(
                        f"Inside an active virtualenv [success]{venv_in_env}[/], reusing it.\n"
                        "Set env var [success]PDM_IGNORE_ACTIVE_VENV[/] to ignore it."
                    )
                    return python
            # otherwise, get a venv associated with the project
            for _, venv in iter_venvs(self):
                python = PythonInfo.from_path(get_venv_python(venv))
                if match_version(python):
                    note(f"Virtualenv [success]{venv}[/] is reused.")
                    self.python = python
                    return python

            if not self.root.joinpath("__pypackages__").exists():
                note("python.use_venv is on, creating a virtualenv for this project...")
                venv = self._create_virtualenv()
                self.python = PythonInfo.from_path(get_venv_python(venv))
                return self.python

        for py_version in self.find_interpreters():
            if match_version(py_version):
                if config.get("python.use_venv"):
                    note("[success]__pypackages__[/] is detected, using the PEP 582 mode")
                self.python = py_version
                return py_version

        raise NoPythonVersion(f"No Python that satisfies {self.python_requires} is found on the system.")

    def get_environment(self) -> BaseEnvironment:
        """Get the environment selected by this project"""

        if self.is_global:
            env = PythonEnvironment(self)
            # Rewrite global project's python requires to be
            # compatible with the exact version
            env.python_requires = PySpecSet(f"=={self.python.version}")
            return env

        return (
            PythonEnvironment(self)
            if self.config["python.use_venv"] and self.python.is_venv
            else PythonLocalEnvironment(self)
        )

    def _create_virtualenv(self) -> Path:
        from pdm.cli.commands.venv.backends import BACKENDS

        backend: str = self.config["venv.backend"]
        venv_backend = BACKENDS[backend](self, None)
        path = venv_backend.create(
            force=True,
            in_project=self.config["venv.in_project"],
            prompt=self.config["venv.prompt"],
            with_pip=self.config["venv.with_pip"],
        )
        self.core.ui.echo(f"Virtualenv is created successfully at [success]{path}[/]", err=True)
        return path

    @property
    def environment(self) -> BaseEnvironment:
        if not self._environment:
            self._environment = self.get_environment()
        return self._environment

    @environment.setter
    def environment(self, value: BaseEnvironment) -> None:
        self._environment = value

    @property
    def python_requires(self) -> PySpecSet:
        return PySpecSet(self.pyproject.metadata.get("requires-python", ""))

    def get_dependencies(self, group: str | None = None) -> dict[str, Requirement]:
        metadata = self.pyproject.metadata
        group = group or "default"
        optional_dependencies = metadata.get("optional-dependencies", {})
        dev_dependencies = self.pyproject.settings.get("dev-dependencies", {})
        in_metadata = group == "default" or group in optional_dependencies
        if group == "default":
            deps = metadata.get("dependencies", [])
        else:
            if group in optional_dependencies and group in dev_dependencies:
                self.core.ui.echo(
                    f"The {group} group exists in both [optional-dependencies] "
                    "and [dev-dependencies], the former is taken.",
                    err=True,
                    style="warning",
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
                    if in_metadata:
                        self.core.ui.echo(
                            f"WARNING: Skipping editable dependency [b]{line}[/] in the"
                            r" [success]\[project][/] table. Please move it to the "
                            r"[success]\[tool.pdm.dev-dependencies][/] table",
                            err=True,
                            style="warning",
                        )
                        continue
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
        dev_group = self.pyproject.settings.get("dev-dependencies", {})
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
        if self.pyproject.metadata.get("optional-dependencies"):
            groups.update(self.pyproject.metadata["optional-dependencies"].keys())
        if self.pyproject.settings.get("dev-dependencies"):
            groups.update(self.pyproject.settings["dev-dependencies"].keys())
        return groups

    @property
    def all_dependencies(self) -> dict[str, dict[str, Requirement]]:
        return {group: self.get_dependencies(group) for group in self.iter_groups()}

    @property
    def allow_prereleases(self) -> bool | None:
        return self.pyproject.settings.get("allow_prereleases")

    @property
    def default_source(self) -> RepositoryConfig:
        """Get the default source from the pypi setting"""
        return RepositoryConfig(
            name="pypi",
            url=self.config["pypi.url"],
            verify_ssl=self.config["pypi.verify_ssl"],
            username=self.config.get("pypi.username"),
            password=self.config.get("pypi.password"),
        )

    @property
    def sources(self) -> list[RepositoryConfig]:
        result: dict[str, RepositoryConfig] = {}
        for source in self.pyproject.settings.get("source", []):
            result[source["name"]] = RepositoryConfig(**source)

        def merge_sources(other_sources: Iterable[tuple[str, RepositoryConfig]]) -> None:
            for name, source in other_sources:
                source.name = name
                if name in result:
                    result[name].passive_update(source)
                else:
                    result[name] = source

        if not self.config.get("pypi.ignore_stored_index", False):
            if "pypi" not in result:  # put pypi source at the beginning
                result = {"pypi": self.default_source, **result}
            else:
                result["pypi"].passive_update(self.default_source)
            merge_sources(self.project_config.iter_sources())
            merge_sources(self.global_config.iter_sources())
        for source in result.values():
            assert source.url, "Source URL must not be empty"
            source.url = expand_env_vars_in_auth(source.url)
        return list(result.values())

    def get_repository(
        self, cls: type[BaseRepository] | None = None, ignore_compatibility: bool = True
    ) -> BaseRepository:
        """Get the repository object"""
        if cls is None:
            cls = self.core.repository_class
        sources = self.sources or []
        return cls(sources, self.environment, ignore_compatibility=ignore_compatibility)

    @property
    def locked_repository(self) -> LockedRepository:
        try:
            lockfile = self.lockfile._data.unwrap()
        except ProjectError:
            lockfile = {}

        return LockedRepository(lockfile, self.sources, self.environment)

    def get_provider(
        self,
        strategy: str = "all",
        tracked_names: Iterable[str] | None = None,
        for_install: bool = False,
        ignore_compatibility: bool = True,
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

        repository = self.get_repository(ignore_compatibility=ignore_compatibility)
        allow_prereleases = self.allow_prereleases
        overrides = {normalize_name(k): v for k, v in self.pyproject.resolution_overrides.items()}
        locked_repository: LockedRepository | None = None
        if strategy != "all" or for_install:
            try:
                locked_repository = self.locked_repository
            except Exception:
                if for_install:
                    raise
                self.core.ui.echo(
                    "Unable to reuse the lock file as it is not compatible with PDM",
                    style="warning",
                    err=True,
                )

        if locked_repository is None:
            return BaseProvider(repository, allow_prereleases, overrides)
        if for_install:
            return BaseProvider(locked_repository, allow_prereleases, overrides)
        provider_class = ReusePinProvider if strategy == "reuse" else EagerUpdateProvider
        tracked_names = [strip_extras(name)[0] for name in tracked_names or ()]
        return provider_class(
            locked_repository.all_candidates,
            tracked_names,
            repository,
            allow_prereleases,
            overrides,
        )

    def get_reporter(
        self,
        requirements: list[Requirement],
        tracked_names: Iterable[str] | None = None,
        spinner: Spinner | None = None,
    ) -> BaseReporter:
        """Return the reporter object to construct a resolver.

        :param requirements: requirements to resolve
        :param tracked_names: the names of packages that needs to update
        :param spinner: optional spinner object
        :returns: a reporter
        """
        from pdm.resolver.reporters import SpinnerReporter

        if spinner is None:
            spinner = termui.SilentSpinner("")

        return SpinnerReporter(spinner, requirements)

    def get_lock_metadata(self, groups: Iterable[str] | None = None) -> dict[str, Any]:
        content_hash = tomlkit.string("sha256:" + self.pyproject.content_hash("sha256"))
        content_hash.trivia.trail = "\n\n"
        if groups is None:
            groups = self.iter_groups()
        return {
            "lock_version": self.lockfile.spec_version,
            "groups": sorted(groups, key=lambda x: (x != "default", x)),
            "content_hash": content_hash,
        }

    def write_lockfile(
        self, toml_data: dict, show_message: bool = True, write: bool = True, groups: Iterable[str] | None = None
    ) -> None:
        """Write the lock file to disk."""
        toml_data["metadata"].update(self.get_lock_metadata(groups))
        self.lockfile.set_data(toml_data)

        if write:
            self.lockfile.write(show_message)

    def make_self_candidate(self, editable: bool = True) -> Candidate:
        req = parse_requirement(path_to_url(self.root.as_posix()), editable)
        assert self.name
        req.name = self.name
        can = make_candidate(req, name=self.name, link=Link.from_path(self.root))
        can.prepare(self.environment).metadata
        return can

    def is_lockfile_hash_match(self) -> bool:
        hash_in_lockfile = str(self.lockfile.hash)
        if not hash_in_lockfile:
            return False
        algo, hash_value = hash_in_lockfile.split(":")
        content_hash = self.pyproject.content_hash(algo)
        return content_hash == hash_value

    def is_lockfile_compatible(self) -> bool:
        """Within the same major version, the higher lockfile generator can work with
        lower lockfile but not vice versa.
        """
        if not self.lockfile.exists():
            return True
        lockfile_version = str(self.lockfile.file_version)
        if not lockfile_version:
            return False
        if "." not in lockfile_version:
            lockfile_version += ".0"
        accepted = get_specifier(f"~={lockfile_version},>={lockfile_version}")
        return accepted.contains(self.lockfile.spec_version)

    def get_pyproject_dependencies(self, group: str, dev: bool = False) -> tuple[list[str], bool]:
        """Get the dependencies array in the pyproject.toml
        Return a tuple of two elements, the first is the dependencies array,
        and the second tells whether it is a dev-dependencies group.
        """
        metadata, settings = self.pyproject.metadata, self.pyproject.settings
        if group == "default":
            return metadata.setdefault("dependencies", []), False
        deps_dict = {
            False: metadata.get("optional-dependencies", {}),
            True: settings.get("dev-dependencies", {}),
        }
        for is_dev, deps in deps_dict.items():
            if group in deps:
                return deps[group], is_dev
        if dev:
            return (
                settings.setdefault("dev-dependencies", {}).setdefault(group, []),
                dev,
            )
        else:
            return (
                metadata.setdefault("optional-dependencies", {}).setdefault(group, []),
                dev,
            )

    def add_dependencies(
        self,
        requirements: dict[str, Requirement],
        to_group: str = "default",
        dev: bool = False,
        show_message: bool = True,
    ) -> None:
        deps, is_dev = self.get_pyproject_dependencies(to_group, dev)
        cast(Array, deps).multiline(True)
        for _, dep in requirements.items():
            matched_index = next(
                (i for i, r in enumerate(deps) if dep.matches(r)),
                None,
            )
            req = dep.as_line()
            if matched_index is None:
                deps.append(req)
            else:
                deps[matched_index] = req
        self.pyproject.write(show_message)

    def init_global_project(self) -> None:
        if not self.is_global or not self.pyproject.empty():
            return
        self.root.mkdir(parents=True, exist_ok=True)
        self.pyproject.set_data({"project": {"dependencies": ["pip", "setuptools", "wheel"]}})
        self.pyproject.write()

    @property
    def backend(self) -> BuildBackend:
        return get_backend_by_spec(self.pyproject.build_system)(self.root)

    @property
    def cache_dir(self) -> Path:
        return Path(self.config.get("cache_dir", ""))

    def cache(self, name: str) -> Path:
        path = self.cache_dir / name
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            # The path could be not accessible
            pass
        return path

    def make_wheel_cache(self) -> WheelCache:
        return WheelCache(self.cache("wheels"))

    def make_candidate_info_cache(self) -> CandidateInfoCache:
        python_hash = hashlib.sha1(str(self.environment.python_requires).encode()).hexdigest()
        file_name = f"package_meta_{python_hash}.json"
        return CandidateInfoCache(self.cache("metadata") / file_name)

    def make_hash_cache(self) -> HashCache:
        return HashCache(directory=self.cache("hashes"))

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
            python = shutil.which("python")
            if python:
                yield PythonInfo.from_path(python)
            args = []
        else:
            if not all(c.isdigit() for c in python_spec.split(".")):
                path = Path(python_spec)
                if path.exists():
                    python = find_python_in_path(python_spec)
                    if python:
                        yield PythonInfo.from_path(python)
                if len(path.parts) == 1:  # only check for spec with only one part
                    python = shutil.which(python_spec)
                    if python:
                        yield PythonInfo.from_path(python)
                return
            args = [int(v) for v in python_spec.split(".") if v != ""]
        finder = self._get_python_finder()
        for entry in finder.find_all(*args):
            yield PythonInfo(entry)
        if not python_spec:
            # Lastly, return the host Python as well
            this_python = getattr(sys, "_base_executable", sys.executable)
            yield PythonInfo.from_path(this_python)

    def _get_python_finder(self) -> Finder:
        from pdm.cli.commands.venv.utils import VenvProvider

        finder = Finder(resolve_symlinks=True)
        if self.config["python.use_venv"]:
            finder.add_provider(VenvProvider(self), 0)
        return finder

    # compatibility, shouldn't be used directly
    @property
    def meta(self) -> dict[str, Any]:
        deprecation_warning("project.meta is deprecated, use project.pyproject.metadata instead")
        return self.pyproject.metadata

    @property
    def tool_settings(self) -> dict[str, Any]:
        deprecation_warning("project.tool_settings is deprecated, use project.pyproject.settings instead")
        return self.pyproject.settings
