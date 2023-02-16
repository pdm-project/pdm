from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Generator

import unearth

from pdm import termui
from pdm.compat import cached_property
from pdm.exceptions import BuildError, PdmUsageError
from pdm.models.auth import PdmBasicAuth
from pdm.models.in_process import (
    get_pep508_environment,
    get_python_abi_tag,
    get_sys_config_paths,
)
from pdm.models.python import PythonInfo
from pdm.models.session import PDMSession
from pdm.models.working_set import WorkingSet
from pdm.utils import (
    get_index_urls,
    get_venv_like_prefix,
    is_pip_compatible_with_python,
    pdm_scheme,
)

if TYPE_CHECKING:
    from pdm._types import Source
    from pdm.project import Project


def _get_shebang_path(executable: str, is_launcher: bool) -> bytes:
    """Get the interpreter path in the shebang line

    The launcher can just use the command as-is.
    Otherwise if the path contains whitespace or is too long, both distlib
    and installer use a clever hack to make the shebang after ``/bin/sh``,
    where the interpreter path is quoted.
    """
    if is_launcher or " " not in executable and (len(executable) + 3) <= 127:
        return executable.encode("utf-8")
    return shlex.quote(executable).encode("utf-8")


def _replace_shebang(contents: bytes, new_executable: bytes) -> bytes:
    """Replace the python executable from the shebeng line, which can be in two forms:

    1. #!python_executable
    2. #!/bin/sh
       '''exec' '/path to/python' "$0" "$@"
       ' '''
    """
    _complex_shebang_re = rb"^'''exec' ('.+?') \"\$0\""
    _simple_shebang_re = rb"^#!(.+?)\s*$"
    match = re.search(_complex_shebang_re, contents, flags=re.M)
    if match:
        return contents.replace(match.group(1), new_executable, 1)
    match = re.search(_simple_shebang_re, contents, flags=re.M)
    if match:
        return contents.replace(match.group(1), new_executable, 1)
    return contents


class PackageFinder(unearth.PackageFinder):
    def _sort_key(self, package: unearth.Package) -> tuple:
        key = super()._sort_key(package)
        *front, last = key
        # prefer wheel if all others are equal
        return (*front, package.link.is_wheel, last)


class Environment:
    """Environment dependent stuff related to the selected Python interpreter."""

    interpreter: PythonInfo
    is_global = False

    def __init__(self, project: Project) -> None:
        """
        :param project: the project instance
        """
        self.python_requires = project.python_requires
        self.project = project
        self.interpreter = project.python
        self.auth = PdmBasicAuth(
            self.project.sources,
            self.project.core.ui.verbosity >= termui.Verbosity.DETAIL,
        )

    def get_paths(self) -> dict[str, str]:
        """Get paths like ``sysconfig.get_paths()`` for installation."""
        return pdm_scheme(str(self.packages_path))

    @cached_property
    def packages_path(self) -> Path:
        """The local packages path."""
        pypackages = self.project.root / "__pypackages__" / self.interpreter.identifier
        if not pypackages.exists() and "-32" in pypackages.name:
            compatible_packages = pypackages.with_name(pypackages.name[:-3])
            if compatible_packages.exists():
                pypackages = compatible_packages
        scripts = "Scripts" if os.name == "nt" else "bin"
        if not pypackages.parent.exists():
            pypackages.parent.mkdir(parents=True)
            pypackages.parent.joinpath(".gitignore").write_text("*\n!.gitignore\n")
        for subdir in [scripts, "include", "lib"]:
            pypackages.joinpath(subdir).mkdir(exist_ok=True, parents=True)
        return pypackages

    @cached_property
    def venv_path(self) -> Path | None:
        """The path of the venv (None if this isn't a venv)"""
        if not self.is_global:
            return None
        return get_venv_like_prefix(self.interpreter.executable)

    @cached_property
    def target_python(self) -> unearth.TargetPython:
        python_version = self.interpreter.version_tuple
        python_abi_tag = get_python_abi_tag(str(self.interpreter.executable))
        return unearth.TargetPython(python_version, [python_abi_tag])

    def _build_session(self, index_urls: list[str], trusted_hosts: list[str]) -> PDMSession:
        ca_certs = self.project.config.get("pypi.ca_certs")
        session = PDMSession(
            cache_dir=self.project.cache("http"),
            index_urls=index_urls,
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
    def get_finder(
        self,
        sources: list[Source] | None = None,
        ignore_compatibility: bool = False,
    ) -> Generator[unearth.PackageFinder, None, None]:
        """Return the package finder of given index sources.

        :param sources: a list of sources the finder should search in.
        :param ignore_compatibility: whether to ignore the python version
            and wheel tags.
        """
        if sources is None:
            sources = self.project.sources
        if not sources:
            raise PdmUsageError(
                "You must specify at least one index in pyproject.toml or config.\n"
                "The 'pypi.ignore_stored_index' config value is "
                f"{self.project.config['pypi.ignore_stored_index']}"
            )

        index_urls, find_links, trusted_hosts = get_index_urls(sources)

        session = self._build_session(index_urls, trusted_hosts)
        finder = PackageFinder(
            session=session,
            index_urls=index_urls,
            find_links=find_links,
            target_python=self.target_python,
            ignore_compatibility=ignore_compatibility,
            no_binary=os.getenv("PDM_NO_BINARY", "").split(","),
            only_binary=os.getenv("PDM_ONLY_BINARY", "").split(","),
            respect_source_order=self.project.pyproject.settings.get("resolution", {}).get(
                "respect-source-order", False
            ),
            verbosity=self.project.core.ui.verbosity,
        )
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

    def update_shebangs(self, new_path: str) -> None:
        """Update the shebang lines"""
        scripts = self.get_paths()["scripts"]
        for child in Path(scripts).iterdir():
            if not child.is_file() or child.suffix not in (".exe", ".py", ""):
                continue
            is_launcher = child.suffix == ".exe"
            new_shebang = _get_shebang_path(new_path, is_launcher)
            child.write_bytes(_replace_shebang(child.read_bytes(), new_shebang))

    def _download_pip_wheel(self, path: str | Path) -> None:
        download_error = BuildError("Can't get a working copy of pip for the project")
        with self.get_finder([self.project.default_source]) as finder:
            finder.only_binary = ["pip"]
            best_match = finder.find_best_match("pip").best
            if not best_match:
                raise download_error
            with tempfile.TemporaryDirectory(prefix="pip-download-") as dirname:
                try:
                    downloaded = finder.download_and_unpack(best_match.link, dirname, dirname)
                except unearth.UnpackError as e:
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


class GlobalEnvironment(Environment):
    """Global environment"""

    is_global = True

    def get_paths(self) -> dict[str, str]:
        is_venv = bool(get_venv_like_prefix(self.interpreter.executable))
        paths = get_sys_config_paths(
            str(self.interpreter.executable),
            kind="user" if not is_venv and self.project.global_config["global_project.user_site"] else "default",
        )
        if is_venv:
            python_xy = f"python{self.interpreter.identifier}"
            paths["include"] = os.path.join(paths["data"], "include", "site", python_xy)
        paths["prefix"] = paths["data"]
        paths["headers"] = paths["include"]
        return paths

    @property
    def packages_path(self) -> Path | None:  # type: ignore[override]
        return None


class PrefixEnvironment(Environment):
    """An environment whose install scheme depends on the given prefix"""

    def __init__(self, project: Project, prefix: str) -> None:
        super().__init__(project)
        self.prefix = prefix

    @property
    def packages_path(self) -> Path | None:  # type: ignore[override]
        return None

    def get_paths(self) -> dict[str, str]:
        paths = get_sys_config_paths(
            str(self.interpreter.executable),
            {"base": self.prefix, "platbase": self.prefix},
            kind="prefix",
        )
        paths["prefix"] = paths["data"]
        paths["headers"] = paths["include"]
        return paths


class BareEnvironment(Environment):
    """Bare environment that does not depend on project files."""

    def __init__(self, project: Project) -> None:
        self.python_requires = project.python_requires
        self.project = project
        self.interpreter = PythonInfo.from_path(sys.executable)
        self.auth = PdmBasicAuth(
            self.project.sources,
            self.project.core.ui.verbosity >= termui.Verbosity.DETAIL,
        )

    def get_working_set(self) -> WorkingSet:
        if self.project.project_config.config_file.exists():
            return self.project.get_environment().get_working_set()
        else:
            return WorkingSet([])
