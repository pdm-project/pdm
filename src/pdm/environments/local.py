from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from typing import TYPE_CHECKING

from pdm.environments.prefix import PrefixEnvironment

if TYPE_CHECKING:
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


class PythonLocalEnvironment(PrefixEnvironment):
    """A project environment that installs packages into
    the local `__pypackages__` directory(PEP 582).
    """

    is_local = True

    def __init__(self, project: Project) -> None:
        prefix = os.path.join(project.root, "__pypackages__")
        super().__init__(project, prefix=prefix)

    @property
    def process_env(self) -> dict[str, str]:
        from pdm.cli.utils import get_pep582_path

        env = super().process_env
        pythonpath = os.getenv("PYTHONPATH", "").split(os.pathsep)
        pythonpath = [get_pep582_path(self.project)] + [
            p for p in pythonpath if "/pep582" not in p.replace("\\", "/")
        ]
        env["PYTHONPATH"] = os.pathsep.join(pythonpath)
        return env

    def update_shebangs(self, new_path: str) -> None:
        """Update the shebang lines"""
        scripts = self.get_paths()["scripts"]
        for child in Path(scripts).iterdir():
            if not child.is_file() or child.suffix not in (".exe", ".py", ""):
                continue
            is_launcher = child.suffix == ".exe"
            new_shebang = _get_shebang_path(new_path, is_launcher)
            child.write_bytes(_replace_shebang(child.read_bytes(), new_shebang))
