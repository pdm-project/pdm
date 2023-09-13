from __future__ import annotations

import contextlib
import hashlib
import os
import re
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable, Mapping, cast

import tomlkit
from tomlkit.items import Array

from pdm import termui
from pdm._types import RepositoryConfig
from pdm.compat import cached_property
from pdm.exceptions import NoPythonVersion, PdmUsageError, ProjectError
from pdm.models.backends import BuildBackend, get_backend_by_spec
from pdm.models.python import PythonInfo
from pdm.models.repositories import BaseRepository, LockedRepository
from pdm.models.requirements import Requirement, parse_requirement, strip_extras
from pdm.models.specifiers import PySpecSet
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
    from findpython import Finder
    from resolvelib.reporters import BaseReporter

    from pdm._types import Spinner
    from pdm.core import Core
    from pdm.environments import BaseEnvironment
    from pdm.models.caches import CandidateInfoCache, HashCache, WheelCache
    from pdm.models.candidates import Candidate
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
        import platformdirs

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
        self.enable_write_lockfile = os.getenv("PDM_NO_LOCK", "0").lower() not in ("1", "true")
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

    @cached_property
    def config(self) -> Mapping[str, Any]:
        """A read-only dict configuration"""
        import collections

        return collections.ChainMap(self.project_config, self.global_config)

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
        self.root.mkdir(parents=True, exist_ok=True)
        python_file = self.root.joinpath(".pdm-python")
        if value is None:
            with contextlib.suppress(FileNotFoundError):
                python_file.unlink()
            return
        python_file.write_text(value, "utf-8")

    def resolve_interpreter(self) -> PythonInfo:
        """Get the Python interpreter path."""
        from pdm.cli.commands.venv.utils import iter_venvs
        from pdm.models.venv import get_venv_python

        def match_version(python: PythonInfo) -> bool:
            return python.valid and self.python_requires.contains(python.version, True)

        def note(message: str) -> None:
            if not self.is_global:
                self.core.ui.echo(message, style="info", err=True)

        config = self.config
        saved_path = self._saved_python
        if saved_path and not os.getenv("PDM_IGNORE_SAVED_PYTHON"):
            python = PythonInfo.from_path(saved_path)
            if match_version(python):
                return python
            else:
                note(
                    "The saved Python interpreter doesn't match the project's requirement. "
                    "Trying to find another one."
                )
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
                python = PythonInfo.from_path(venv.interpreter)
                if match_version(python):
                    note(f"Virtualenv [success]{venv.root}[/] is reused.")
                    self.python = python
                    return python

            if not self.root.joinpath("__pypackages__").exists():
                note("python.use_venv is on, creating a virtualenv for this project...")
                venv_path = self._create_virtualenv()
                self.python = PythonInfo.from_path(get_venv_python(venv_path))
                return self.python

        for py_version in self.find_interpreters():
            if match_version(py_version):
                if config.get("python.use_venv"):
                    note("[success]__pypackages__[/] is detected, using the PEP 582 mode")
                self.python = py_version
                return py_version

        raise NoPythonVersion(f"No Python that satisfies {self.python_requires} is found on the system.")

    def get_environment(self) -> BaseEnvironment:
        from pdm.environments import PythonEnvironment, PythonLocalEnvironment

        """Get the environment selected by this project"""

        if self.is_global:
            env = PythonEnvironment(self)
            # Rewrite global project's python requires to be
            # compatible with the exact version
            env.python_requires = PySpecSet(f"=={self.python.version}")
            return env

        return (
            PythonEnvironment(self)
            if self.config["python.use_venv"] and self.python.get_venv() is not None
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
            config_prefix="pypi",
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
            result[source["name"]] = RepositoryConfig(**source, config_prefix="pypi")

        def merge_sources(other_sources: Iterable[RepositoryConfig]) -> None:
            for source in other_sources:
                name = source.name
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
        sources: list[RepositoryConfig] = []
        for source in result.values():
            if not source.url:
                continue
            source.url = expand_env_vars_in_auth(source.url)
            sources.append(source)
        return sources

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

    def get_lock_metadata(self) -> dict[str, Any]:
        content_hash = "sha256:" + self.pyproject.content_hash("sha256")
        return {"lock_version": self.lockfile.spec_version, "content_hash": content_hash}

    def write_lockfile(self, toml_data: dict, show_message: bool = True, write: bool = True, **_kwds: Any) -> None:
        """Write the lock file to disk."""
        if _kwds:
            deprecation_warning("Extra arguments have been moved to `format_lockfile` function", stacklevel=2)
        toml_data["metadata"].update(self.get_lock_metadata())
        self.lockfile.set_data(toml_data)

        if write and self.enable_write_lockfile:
            self.lockfile.write(show_message)

    def make_self_candidate(self, editable: bool = True) -> Candidate:
        from unearth import Link

        from pdm.models.candidates import make_candidate

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

    def use_pyproject_dependencies(
        self, group: str, dev: bool = False
    ) -> tuple[list[str], Callable[[list[str]], None]]:
        """Get the dependencies array and setter in the pyproject.toml
        Return a tuple of two elements, the first is the dependencies array,
        and the second value is a callable to set the dependencies array back.
        """

        def update_dev_dependencies(deps: list[str]) -> None:
            from tomlkit.container import OutOfOrderTableProxy

            settings.setdefault("dev-dependencies", {})[group] = deps
            if isinstance(self.pyproject._data["tool"], OutOfOrderTableProxy):
                # In case of a separate table, we have to remove and re-add it to make the write correct.
                # This may change the order of tables in the TOML file, but it's the best we can do.
                # see bug pdm-project/pdm#2056 for details
                del self.pyproject._data["tool"]["pdm"]
                self.pyproject._data["tool"]["pdm"] = settings

        metadata, settings = self.pyproject.metadata, self.pyproject.settings
        if group == "default":
            return metadata.get("dependencies", tomlkit.array()), lambda x: metadata.__setitem__("dependencies", x)
        deps_setter = [
            (
                metadata.get("optional-dependencies", {}),
                lambda x: metadata.setdefault("optional-dependencies", {}).__setitem__(group, x),
            ),
            (settings.get("dev-dependencies", {}), update_dev_dependencies),
        ]
        for deps, setter in deps_setter:
            if group in deps:
                return deps[group], setter
        # If not found, return an empty list and a setter to add the group
        return tomlkit.array(), deps_setter[int(dev)][1]

    def add_dependencies(
        self,
        requirements: dict[str, Requirement],
        to_group: str = "default",
        dev: bool = False,
        show_message: bool = True,
    ) -> None:
        deps, setter = self.use_pyproject_dependencies(to_group, dev)
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
        setter(cast(Array, deps).multiline(True))
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
        from pdm.models.caches import get_wheel_cache

        return get_wheel_cache(self.cache("wheels"))

    def make_candidate_info_cache(self) -> CandidateInfoCache:
        from pdm.models.caches import CandidateInfoCache

        python_hash = hashlib.sha1(str(self.environment.python_requires).encode()).hexdigest()
        file_name = f"package_meta_{python_hash}.json"
        return CandidateInfoCache(self.cache("metadata") / file_name)

    def make_hash_cache(self) -> HashCache:
        from pdm.models.caches import HashCache

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
        finder_arg: str | None = None

        if not python_spec:
            if config.get("python.use_pyenv", True) and os.path.exists(PYENV_ROOT):
                pyenv_shim = os.path.join(PYENV_ROOT, "shims", "python3")
                if os.name == "nt":
                    pyenv_shim += ".bat"
                if os.path.exists(pyenv_shim):
                    yield PythonInfo.from_path(pyenv_shim)
                elif os.path.exists(pyenv_shim.replace("python3", "python")):
                    yield PythonInfo.from_path(pyenv_shim.replace("python3", "python"))
            python = shutil.which("python") or shutil.which("python3")
            if python:
                yield PythonInfo.from_path(python)
        else:
            if not all(c.isdigit() for c in python_spec.split(".")):
                path = Path(python_spec)
                if path.exists():
                    python = find_python_in_path(python_spec)
                    if python:
                        yield PythonInfo.from_path(python)
                        return
                if len(path.parts) == 1:  # only check for spec with only one part
                    python = shutil.which(python_spec)
                    if python:
                        yield PythonInfo.from_path(python)
                        return
            finder_arg = python_spec
        finder = self._get_python_finder()
        for entry in finder.find_all(finder_arg, allow_prereleases=True):
            yield PythonInfo(entry)
        if not python_spec:
            # Lastly, return the host Python as well
            this_python = getattr(sys, "_base_executable", sys.executable)
            yield PythonInfo.from_path(this_python)

    def _get_python_finder(self) -> Finder:
        from findpython import Finder

        from pdm.cli.commands.venv.utils import VenvProvider

        providers: list[str] = self.config["python.providers"]
        finder = Finder(resolve_symlinks=True, selected_providers=providers or None)
        if self.config["python.use_venv"] and (not providers or "venv" in providers):
            venv_pos = providers.index("venv") if providers else 0
            finder.add_provider(VenvProvider(self), venv_pos)
        return finder

    # compatibility, shouldn't be used directly
    @property
    def meta(self) -> dict[str, Any]:
        deprecation_warning("project.meta is deprecated, use project.pyproject.metadata instead", stacklevel=2)
        return self.pyproject.metadata

    @property
    def tool_settings(self) -> dict[str, Any]:
        deprecation_warning("project.tool_settings is deprecated, use project.pyproject.settings instead", stacklevel=2)
        return self.pyproject.settings
