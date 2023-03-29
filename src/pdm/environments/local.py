from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from typing import TYPE_CHECKING

from pdm.compat import cached_property
from pdm.environments.base import BaseEnvironment
from pdm.utils import pdm_scheme

if TYPE_CHECKING:
    pass


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


class PythonLocalEnvironment(BaseEnvironment):
    """A project environment that installs packages into
    the local `__pypackages__` directory(PEP 582).
    """

    is_local = True

    @property
    def process_env(self) -> dict[str, str]:
        from pdm.cli.utils import get_pep582_path

        env = super().process_env
        pythonpath = os.getenv("PYTHONPATH", "").split(os.pathsep)
        pythonpath = [get_pep582_path(self.project)] + [p for p in pythonpath if "/pep582" not in p.replace("\\", "/")]
        env["PYTHONPATH"] = os.pathsep.join(pythonpath)
        env["PEP582_PACKAGES"] = str(self.packages_path)
        return env

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

    def get_paths(self) -> dict[str, str]:
        return pdm_scheme(self.packages_path.as_posix())

    def update_shebangs(self, new_path: str) -> None:
        """Update the shebang lines"""
        scripts = self.get_paths()["scripts"]
        for child in Path(scripts).iterdir():
            if not child.is_file() or child.suffix not in (".exe", ".py", ""):
                continue
            is_launcher = child.suffix == ".exe"
            new_shebang = _get_shebang_path(new_path, is_launcher)
            child.write_bytes(_replace_shebang(child.read_bytes(), new_shebang))
