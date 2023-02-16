from __future__ import annotations

import base64
import hashlib
import sys
from pathlib import Path
from typing import Iterable, TypeVar
from findpython import PythonVersion

from findpython.providers import BaseProvider

from pdm.project import Project

IS_WIN = sys.platform == "win32"
BIN_DIR = "Scripts" if IS_WIN else "bin"


def hash_path(path: str) -> str:
    """Generate a hash for the given path."""
    return base64.urlsafe_b64encode(hashlib.new("md5", path.encode(), usedforsecurity=False).digest()).decode()[:8]


def get_in_project_venv_python(root: Path) -> Path | None:
    """Get the python interpreter path of venv-in-project"""
    for possible_dir in (".venv", "venv", "env"):
        venv_python = get_venv_python(root / possible_dir)
        if venv_python.exists():
            return venv_python
    return None


def get_venv_prefix(project: Project) -> str:
    """Get the venv prefix for the project"""
    path = project.root
    name_hash = hash_path(path.as_posix())
    return f"{path.name}-{name_hash}-"


def iter_venvs(project: Project) -> Iterable[tuple[str, Path]]:
    """Return an iterable of venv paths associated with the project"""
    in_project_venv_python = get_in_project_venv_python(project.root)
    if in_project_venv_python is not None:
        yield "in-project", Path(in_project_venv_python).parent.parent
    venv_prefix = get_venv_prefix(project)
    venv_parent = Path(project.config["venv.location"])
    for venv in venv_parent.glob(f"{venv_prefix}*"):
        ident = venv.name[len(venv_prefix) :]
        yield ident, venv


def get_venv_python(venv: Path) -> Path:
    """Get the interpreter path inside the given venv."""
    suffix = ".exe" if IS_WIN else ""
    return venv / BIN_DIR / f"python{suffix}"


def iter_central_venvs(project: Project) -> Iterable[tuple[str, Path]]:
    """Return an iterable of all managed venvs and their paths."""
    venv_parent = Path(project.config["venv.location"])
    for venv in venv_parent.glob("*"):
        ident = venv.name
        yield ident, venv


T = TypeVar("T", bound=BaseProvider)


class VenvProvider(BaseProvider):
    """A Python provider for project venv pythons"""

    def __init__(self, project: Project) -> None:
        self.project = project

    @classmethod
    def create(cls: type[T]) -> T | None:  # pragma: no cover
        return None

    def find_pythons(self) -> Iterable[PythonVersion]:
        for _, venv in iter_venvs(self.project):
            python = get_venv_python(venv)
            if python.exists():
                yield PythonVersion(python, _interpreter=python, keep_symlink=True)
