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

from pdm import termui
from pdm.exceptions import BuildError
from pdm.models import pip_shims
from pdm.models.auth import make_basic_auth
from pdm.models.in_process import (
    get_pep508_environment,
    get_python_abi_tag,
    get_sys_config_paths,
)
from pdm.models.working_set import WorkingSet
from pdm.utils import cached_property, get_finder, is_venv_python, pdm_scheme

if TYPE_CHECKING:
    from pdm._types import Source
    from pdm.models.python import PythonInfo
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
    else:
        match = re.search(_simple_shebang_re, contents, flags=re.M)
        assert match is not None
        return contents.replace(match.group(1), new_executable, 1)


class Environment:
    """Environment dependent stuff related to the selected Python interpreter."""

    is_global = False

    def __init__(self, project: Project) -> None:
        """
        :param project: the project instance
        """
        self.python_requires = project.python_requires
        self.project = project
        self.interpreter: PythonInfo = project.python
        self._essential_installed = False
        self.auth = make_basic_auth(
            self.project.sources, self.project.core.ui.verbosity >= termui.DETAIL
        )

    def get_paths(self) -> dict[str, str]:
        """Get paths like ``sysconfig.get_paths()`` for installation."""
        return pdm_scheme(str(self.packages_path))

    @cached_property
    def packages_path(self) -> Path:
        """The local packages path."""
        pypackages = (
            self.project.root  # type: ignore
            / "__pypackages__"
            / self.interpreter.identifier
        )
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

    @contextmanager
    def get_finder(
        self,
        sources: list[Source] | None = None,
        ignore_requires_python: bool = False,
    ) -> Generator[pip_shims.PackageFinder, None, None]:
        """Return the package finder of given index sources.

        :param sources: a list of sources the finder should search in.
        :param ignore_requires_python: whether to ignore the python version constraint.
        """
        if sources is None:
            sources = self.project.sources

        python_version = self.interpreter.version_tuple
        python_abi_tag = get_python_abi_tag(str(self.interpreter.executable))
        finder = get_finder(
            sources,
            self.project.cache_dir.as_posix(),
            python_version,
            python_abi_tag,
            ignore_requires_python,
        )
        # Reuse the auth across sessions to avoid prompting repeatedly.
        finder.session.auth = self.auth  # type: ignore
        yield finder
        finder.session.close()  # type: ignore

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
            python = os.path.splitext(command)[0]
            version = python[6:]
            this_version = self.interpreter.version
            if not version or str(this_version).startswith(version):
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
        dirname = Path(tempfile.mkdtemp(prefix="pip-download-"))
        try:
            subprocess.check_call(
                [
                    getattr(sys, "_original_executable", sys.executable),
                    "-m",
                    "pip",
                    "download",
                    "--only-binary=:all:",
                    "-d",
                    str(dirname),
                    "pip<21",  # pip>=21 drops the support of py27
                ],
            )
            wheel_file = next(dirname.glob("pip-*.whl"))
            shutil.move(str(wheel_file), path)
        except subprocess.CalledProcessError:
            raise BuildError("Failed to download pip for the given interpreter")
        finally:
            shutil.rmtree(dirname, ignore_errors=True)

    @cached_property
    def pip_command(self) -> list[str]:
        """Get a pip command for this environment, and download one if not available.
        Return a list of args like ['python', '-m', 'pip']
        """
        from pip import __file__ as pip_location

        python_major = self.interpreter.major
        executable = str(self.interpreter.executable)
        proc = subprocess.run(
            [executable, "-Esm", "pip", "--version"], capture_output=True
        )
        if proc.returncode == 0:
            # The pip has already been installed with the executable, just use it
            return [executable, "-Esm", "pip"]
        if python_major == 3:
            # Use the host pip package.
            return [executable, "-Es", os.path.dirname(pip_location)]
        # For py2, only pip<21 is eligible, download a pip wheel from the Internet.
        pip_wheel = self.project.cache_dir / "pip.whl"
        if not pip_wheel.is_file():
            self._download_pip_wheel(pip_wheel)
        return [executable, str(pip_wheel / "pip")]


class GlobalEnvironment(Environment):
    """Global environment"""

    is_global = True

    def get_paths(self) -> dict[str, str]:
        is_venv = is_venv_python(self.interpreter.executable)
        paths = get_sys_config_paths(
            str(self.interpreter.executable),
            user_site=not is_venv
            and self.project.global_config["global_project.user_site"],
        )
        if is_venv:
            python_xy = f"python{self.interpreter.identifier}"
            paths["include"] = os.path.join(paths["data"], "include", "site", python_xy)
        paths["prefix"] = paths["data"]
        paths["headers"] = paths["include"]
        return paths

    @property
    def packages_path(self) -> Path | None:  # type: ignore
        return None
