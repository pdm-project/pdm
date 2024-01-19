from __future__ import annotations

import os
import re
import shlex
from functools import cached_property
from pathlib import Path

from pdm.environments.base import BaseEnvironment
from pdm.utils import pdm_scheme


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


def _is_console_script(content: bytes) -> bool:
    import io
    import zipfile

    if os.name == "nt":  # Windows .exe should be a zip file.
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                return zf.namelist() == ["__main__.py"]
        except zipfile.BadZipFile:
            return False

    try:
        text = content.decode("utf-8")
        return text.startswith("#!")
    except UnicodeDecodeError:
        return False


def _replace_shebang(path: Path, new_executable: bytes) -> None:
    """Replace the python executable from the shebeng line, which can be in two forms:

    1. #!python_executable
    2. #!/bin/sh
       '''exec' '/path to/python' "$0" "$@"
       ' '''
    """
    _complex_shebang_re = rb"^(#!/bin/sh\n'''exec' )('.+?')( \"\$0\")"
    _simple_shebang_re = rb"^(#!)(.+?)\s*(?=\n)"
    contents = path.read_bytes()

    if not _is_console_script(contents):
        return

    if os.name == "nt":
        new_content, count = re.subn(_simple_shebang_re, rb"\1" + new_executable, contents, count=1, flags=re.M)
        if count > 0:
            path.write_bytes(new_content)
        return

    new_content, count = re.subn(_complex_shebang_re, rb"\1" + new_executable + rb"\3", contents, count=1)
    if count > 0:
        path.write_bytes(new_content)
        return

    new_content, count = re.subn(_simple_shebang_re, rb"\1" + new_executable, contents, count=1)
    if count > 0:
        path.write_bytes(new_content)


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

    def get_paths(self, dist_name: str | None = None) -> dict[str, str]:
        scheme = pdm_scheme(self.packages_path.as_posix())
        scheme["headers"] = os.path.join(scheme["headers"], dist_name or "UNKNOWN")
        return scheme

    def update_shebangs(self, new_path: str) -> None:
        """Update the shebang lines"""
        scripts = self.get_paths()["scripts"]
        for child in Path(scripts).iterdir():
            if not child.is_file() or child.suffix not in (".exe", ".py", ""):
                continue
            is_launcher = child.suffix == ".exe"
            new_shebang = _get_shebang_path(new_path, is_launcher)
            _replace_shebang(child, new_shebang)
