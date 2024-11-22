from __future__ import annotations

import abc
import os
import re
import shutil
import subprocess
import sys
import tempfile
import weakref
from contextlib import contextmanager
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Generator

from pdm._types import NotSet, NotSetType
from pdm.exceptions import BuildError, PdmUsageError
from pdm.models.in_process import get_env_spec
from pdm.models.markers import EnvSpec
from pdm.models.python import PythonInfo
from pdm.models.working_set import WorkingSet
from pdm.utils import deprecation_warning, is_pip_compatible_with_python

if TYPE_CHECKING:
    import unearth
    from httpx import BaseTransport

    from pdm._types import RepositoryConfig
    from pdm.models.session import PDMPyPIClient
    from pdm.project import Project


class BaseEnvironment(abc.ABC):
    """Environment dependent stuff related to the selected Python interpreter."""

    project: Project
    is_local = False

    def __init__(self, project: Project, *, python: str | None = None) -> None:
        """
        :param project: the project instance
        """
        from pdm.models.auth import PdmBasicAuth

        if isinstance(project, weakref.ProxyTypes):
            self.project = project
        else:
            self.project = weakref.proxy(project)
        self.python_requires = project.python_requires
        self.auth = PdmBasicAuth(project.core.ui, self.project.sources)
        if python is None:
            self._interpreter = project.python
        else:
            self._interpreter = PythonInfo.from_path(python)

    @property
    def is_global(self) -> bool:
        """For backward compatibility, it is opposite to ``is_local``."""
        return not self.is_local

    @property
    def interpreter(self) -> PythonInfo:
        return self._interpreter

    @abc.abstractmethod
    def get_paths(self, dist_name: str | None = None) -> dict[str, str]:
        """Get paths like ``sysconfig.get_paths()`` for installation.

        :param dist_name: The package name to be installed, if any.
        """
        ...

    @property
    def process_env(self) -> dict[str, str]:
        """Get the process env var dict for the environment."""
        project = self.project
        this_path = self.get_paths()["scripts"]
        python_root = os.path.dirname(project.python.executable)
        new_path = os.pathsep.join([this_path, os.getenv("PATH", ""), python_root])
        return {"PATH": new_path, "PDM_PROJECT_ROOT": str(project.root)}

    def _build_session(
        self, sources: list[RepositoryConfig] | None = None, mounts: dict[str, BaseTransport | None] | None = None
    ) -> PDMPyPIClient:
        from pdm.models.session import PDMPyPIClient

        if sources is None:
            sources = self.project.sources

        session = PDMPyPIClient(
            sources=sources,
            cache_dir=self.project.cache("http") if self.project.core.state.enable_cache else None,
            timeout=self.project.config["request_timeout"],
            auth=self.auth,
            mounts=mounts,
        )
        self.project.core.exit_stack.callback(session.close)
        return session

    @cached_property
    def session(self) -> PDMPyPIClient:
        """Build the session and cache it."""
        return self._build_session()

    @contextmanager
    def get_finder(
        self,
        sources: list[RepositoryConfig] | None = None,
        ignore_compatibility: bool | NotSetType = NotSet,
        minimal_version: bool = False,
        env_spec: EnvSpec | None = None,
    ) -> Generator[unearth.PackageFinder]:
        """Return the package finder of given index sources.

        :param sources: a list of sources the finder should search in.
        :param ignore_compatibility: (DEPRECATED)whether to ignore the python version
            and wheel tags.
        :param minimal_version: whether to find the minimal version of the package.
        :param env_spec: the environment spec to filter the packages.
        """
        from pdm.models.finder import PDMPackageFinder

        if sources is None:
            sources = self.project.sources
        if not sources:
            raise PdmUsageError(
                "You must specify at least one index in pyproject.toml or config.\n"
                "The 'pypi.ignore_stored_index' config value is "
                f"{self.project.config['pypi.ignore_stored_index']}"
            )
        if ignore_compatibility is not NotSet:  # pragma: no cover
            deprecation_warning(
                "`ignore_compatibility` argument is deprecated, pass in `env_spec` instead.\n",
                stacklevel=2,
            )
        else:
            ignore_compatibility = False

        if env_spec is None:
            if ignore_compatibility:  # pragma: no cover
                env_spec = self.allow_all_spec
            else:
                env_spec = self.spec

        finder = PDMPackageFinder(
            session=self.session,
            env_spec=env_spec,
            no_binary=self._setting_list("PDM_NO_BINARY", "resolution.no-binary"),
            only_binary=self._setting_list("PDM_ONLY_BINARY", "resolution.only-binary"),
            prefer_binary=self._setting_list("PDM_PREFER_BINARY", "resolution.prefer-binary"),
            respect_source_order=self.project.pyproject.settings.get("resolution", {}).get(
                "respect-source-order", False
            ),
            verbosity=self.project.core.ui.verbosity,
            minimal_version=minimal_version,
            exclude_newer_than=self.project.core.state.exclude_newer,
        )
        finder.sources.clear()
        for source in sources:
            assert source.url
            if source.type == "find_links":
                finder.add_find_links(source.url)
            else:
                finder.add_index_url(source.url)
        yield finder

    def _setting_list(self, var: str, key: str) -> list[str]:
        """
        Get a list value, either comma separated or structured.

        Returns `None` if both the environment variable and the key does not exists.
        """
        if value := self.project.env_or_setting(var, key):
            if isinstance(value, str):
                value = [stripped for v in value.split(",") if (stripped := v.strip())]
            return [stripped for v in value if (stripped := v.strip())]
        return []

    def get_working_set(self) -> WorkingSet:
        """Get the working set based on local packages directory."""
        paths = self.get_paths()
        return WorkingSet([paths["platlib"], paths["purelib"]])

    @cached_property
    def spec(self) -> EnvSpec:
        return get_env_spec(self.interpreter.executable.as_posix())

    @property
    def allow_all_spec(self) -> EnvSpec:
        return EnvSpec(self.python_requires._logic)

    def which(self, command: str) -> str | None:
        """Get the full path of the given executable against this environment."""
        if not os.path.isabs(command) and command.startswith("python"):
            match = re.match(r"python(\d(?:\.\d{1,2})?)", command)
            this_version = self.interpreter.version
            if not match or str(this_version).startswith(match.group(1)):
                return str(self.interpreter.executable)
        # Fallback to use shutil.which to find the executable
        this_path = self.get_paths()["scripts"]
        python_root = os.path.dirname(self.interpreter.executable)
        new_path = os.pathsep.join([this_path, os.getenv("PATH", ""), python_root])
        return shutil.which(command, path=new_path)

    def _download_pip_wheel(self, path: str | Path) -> None:  # pragma: no cover
        from unearth import UnpackError

        download_error = BuildError("Can't get a working copy of pip for the project")
        with self.get_finder([self.project.default_source]) as finder:
            finder.only_binary = {"pip"}
            best_match = finder.find_best_match("pip").best
            if not best_match:
                raise download_error
            with tempfile.TemporaryDirectory(prefix="pip-download-") as dirname:
                try:
                    downloaded = finder.download_and_unpack(best_match.link, dirname, dirname)
                except UnpackError as e:
                    raise download_error from e
                shutil.move(str(downloaded), path)

    @cached_property
    def pip_command(self) -> list[str]:
        """Get a pip command for this environment, and download one if not available.
        Return a list of args like ['python', '-m', 'pip']
        """
        try:
            from pip import __file__ as pip_location
        except ImportError:
            pip_location = None  # type: ignore[assignment]

        python_version = self.interpreter.version
        executable = str(self.interpreter.executable)
        proc = subprocess.run([executable, "-Esm", "pip", "--version"], capture_output=True)
        if proc.returncode == 0:
            # The pip has already been installed with the executable, just use it
            command = [executable, "-Esm", "pip"]
        elif pip_location and is_pip_compatible_with_python(python_version):
            # Use the host pip package if available
            command = [executable, "-Es", os.path.dirname(pip_location)]
        else:
            # Otherwise, download a pip wheel from the Internet.
            pip_wheel = self.project.cache_dir / "pip.whl"
            if not pip_wheel.is_file():
                self._download_pip_wheel(pip_wheel)
            command = [executable, str(pip_wheel / "pip")]
        verbosity = self.project.core.ui.verbosity
        if verbosity > 0:
            command.append("-" + "v" * verbosity)
        return command

    @property
    def script_kind(self) -> str:
        from dep_logic.tags.platform import Arch

        if os.name != "nt":
            return "posix"
        if (arch := self.spec.platform.arch) == Arch.X86:  # pragma: no cover
            return "win-ia32"
        elif arch == Arch.Aarch64:  # pragma: no cover
            return "win-arm64"
        else:
            return "win-amd64"


class BareEnvironment(BaseEnvironment):
    """Bare environment that does not depend on project files."""

    def __init__(self, project: Project) -> None:
        super().__init__(project, python=sys.executable)

    def get_paths(self, dist_name: str | None = None) -> dict[str, str]:
        return {}

    def get_working_set(self) -> WorkingSet:
        if self.project.project_config.config_file.exists():
            return self.project.get_environment().get_working_set()
        else:
            return WorkingSet([])
