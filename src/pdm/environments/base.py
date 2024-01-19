from __future__ import annotations

import abc
import functools
import os
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from functools import cached_property, partial
from pathlib import Path
from typing import TYPE_CHECKING, Generator, no_type_check

from pdm.exceptions import BuildError, PdmUsageError
from pdm.models.in_process import get_pep508_environment, get_python_abis, get_uname, sysconfig_get_platform
from pdm.models.python import PythonInfo
from pdm.models.working_set import WorkingSet
from pdm.utils import deprecation_warning, get_trusted_hosts, is_pip_compatible_with_python

if TYPE_CHECKING:
    import unearth

    from pdm._types import RepositoryConfig
    from pdm.models.session import PDMSession
    from pdm.project import Project


@no_type_check
def get_paths_wrapper(get_paths):  # pragma: no cover
    @functools.wraps(get_paths)
    def wrapped(self: BaseEnvironment, dist_name: str | None = None) -> dict[str, str]:
        result = get_paths(self)
        if dist_name and "headers" in result:
            result["headers"] = os.path.join(result["headers"], dist_name)
        return result

    return wrapped


class BaseEnvironment(abc.ABC):
    """Environment dependent stuff related to the selected Python interpreter."""

    is_local = False

    def __init_subclass__(cls) -> None:
        import inspect

        get_paths_params = inspect.signature(cls.get_paths).parameters
        if "dist_name" not in get_paths_params:  # pragma: no cover
            deprecation_warning("get_paths() should accept a `dist_name` argument", stacklevel=3)
            cls.get_paths = get_paths_wrapper(cls.get_paths)  # type: ignore[method-assign]

    def __init__(self, project: Project, *, python: str | None = None) -> None:
        """
        :param project: the project instance
        """
        from pdm.models.auth import PdmBasicAuth

        self.python_requires = project.python_requires
        self.project = project
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

    @cached_property
    def target_python(self) -> unearth.TargetPython:
        from unearth import TargetPython

        python_version = self.interpreter.version_tuple
        python_abis = get_python_abis(str(self.interpreter.executable))
        tp = TargetPython(python_version, python_abis)
        # calculate the target platform tags
        with self._patch_target_python():
            tp.supported_tags()
        return tp

    def _build_session(self, trusted_hosts: list[str]) -> PDMSession:
        from pdm.models.session import PDMSession

        ca_certs = self.project.config.get("pypi.ca_certs")
        session = PDMSession(
            cache_dir=self.project.cache("http"),
            trusted_hosts=trusted_hosts,
            ca_certificates=Path(ca_certs) if ca_certs is not None else None,
        )
        certfn = self.project.config.get("pypi.client_cert")
        if certfn:
            keyfn = self.project.config.get("pypi.client_key")
            session.cert = (Path(certfn), Path(keyfn) if keyfn else None)

        session.auth = self.auth
        return session

    @contextmanager
    def _patch_target_python(self) -> Generator[None, None, None]:
        """Patch the packaging modules to respect the arch of target python."""
        import sysconfig

        import packaging.tags

        old_32bit = packaging.tags._32_BIT_INTERPRETER
        old_os_uname = getattr(os, "uname", None)
        old_get_platform = sysconfig.get_platform

        if old_os_uname is not None:

            def uname() -> os.uname_result:
                return get_uname(str(self.interpreter.path))

            os.uname = uname
        packaging.tags._32_BIT_INTERPRETER = self.interpreter.is_32bit
        sysconfig.get_platform = partial(sysconfig_get_platform, str(self.interpreter.path))
        try:
            yield
        finally:
            sysconfig.get_platform = old_get_platform
            packaging.tags._32_BIT_INTERPRETER = old_32bit
            if old_os_uname is not None:
                os.uname = old_os_uname

    @contextmanager
    def get_finder(
        self,
        sources: list[RepositoryConfig] | None = None,
        ignore_compatibility: bool = False,
        minimal_version: bool = False,
    ) -> Generator[unearth.PackageFinder, None, None]:
        """Return the package finder of given index sources.

        :param sources: a list of sources the finder should search in.
        :param ignore_compatibility: whether to ignore the python version
            and wheel tags.
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

        trusted_hosts = get_trusted_hosts(sources)

        session = self._build_session(trusted_hosts)
        finder = PDMPackageFinder(
            session=session,
            target_python=self.target_python,
            ignore_compatibility=ignore_compatibility,
            no_binary=os.getenv("PDM_NO_BINARY", "").split(","),
            only_binary=os.getenv("PDM_ONLY_BINARY", "").split(","),
            prefer_binary=os.getenv("PDM_PREFER_BINARY", "").split(","),
            respect_source_order=self.project.pyproject.settings.get("resolution", {}).get(
                "respect-source-order", False
            ),
            verbosity=self.project.core.ui.verbosity,
            minimal_version=minimal_version,
        )
        finder.sources.clear()
        for source in sources:
            assert source.url
            if source.type == "find_links":
                finder.add_find_links(source.url)
            else:
                finder.add_index_url(source.url)
        try:
            yield finder
        finally:
            session.close()

    def get_working_set(self) -> WorkingSet:
        """Get the working set based on local packages directory."""
        paths = self.get_paths()
        return WorkingSet([paths["platlib"], paths["purelib"]])

    @cached_property
    def marker_environment(self) -> dict[str, str]:
        """Get environment for marker evaluation"""
        return get_pep508_environment(str(self.interpreter.executable))

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

    def _download_pip_wheel(self, path: str | Path) -> None:
        from unearth import UnpackError

        download_error = BuildError("Can't get a working copy of pip for the project")
        with self.get_finder([self.project.default_source]) as finder:
            finder.only_binary = ["pip"]
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
