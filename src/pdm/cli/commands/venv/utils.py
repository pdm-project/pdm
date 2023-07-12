from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import Iterable, TypeVar

from findpython import BaseProvider, PythonVersion

from pdm.exceptions import PdmUsageError
from pdm.models.venv import VirtualEnv
from pdm.project import Project


def hash_path(path: str) -> str:
    """Generate a hash for the given path."""
    return base64.urlsafe_b64encode(hashlib.new("md5", path.encode(), usedforsecurity=False).digest()).decode()[:8]


def get_in_project_venv(root: Path) -> VirtualEnv | None:
    """Get the python interpreter path of venv-in-project"""
    for possible_dir in (".venv", "venv", "env"):
        venv = VirtualEnv.get(root / possible_dir)
        if venv is not None:
            return venv
    return None


def get_venv_prefix(project: Project) -> str:
    """Get the venv prefix for the project"""
    path = project.root
    name_hash = hash_path(path.as_posix())
    return f"{path.name}-{name_hash}-"


def iter_venvs(project: Project) -> Iterable[tuple[str, VirtualEnv]]:
    """Return an iterable of venv paths associated with the project"""
    in_project_venv = get_in_project_venv(project.root)
    if in_project_venv is not None:
        yield "in-project", in_project_venv
    venv_prefix = get_venv_prefix(project)
    venv_parent = Path(project.config["venv.location"])
    for path in venv_parent.glob(f"{venv_prefix}*"):
        ident = path.name[len(venv_prefix) :]
        venv = VirtualEnv.get(path)
        if venv is not None:
            yield ident, venv


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

    def find_pythons(self) -> list[PythonVersion]:
        results: list[PythonVersion] = []
        for _, venv in iter_venvs(self.project):
            results.append(PythonVersion(venv.interpreter, interpreter=venv.interpreter, keep_symlink=True))
        return results


def get_venv_with_name(project: Project, name: str) -> VirtualEnv:
    all_venvs = dict(iter_venvs(project))
    try:
        return all_venvs[name]
    except KeyError:
        raise PdmUsageError(
            f"No virtualenv with key '{name}' is found, must be one of {list(all_venvs)}.\n"
            "You can create one with 'pdm venv create'.",
        ) from None
