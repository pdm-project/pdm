from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
from typing import TYPE_CHECKING

from findpython import BaseProvider, PythonVersion

from pdm.exceptions import PdmUsageError
from pdm.models.venv import VirtualEnv
from pdm.utils import open_for_write_no_symlink

if TYPE_CHECKING:
    import sys
    from collections.abc import Iterable

    if sys.version_info >= (3, 11):
        from typing import Self
    else:
        from typing_extensions import Self

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


def _get_python_envs_path(project: Project) -> Path:
    return project.root / ".python-envs"


def _read_python_envs(project: Project) -> list[str]:
    path = _get_python_envs_path(project)
    if path.is_symlink():
        raise PdmUsageError(f"Refusing to read from {path} because it is a symlink.")
    try:
        return path.read_text("utf-8").splitlines()
    except FileNotFoundError:
        return []


def _write_python_envs(project: Project, entries: list[str]) -> None:
    with open_for_write_no_symlink(_get_python_envs_path(project)) as fp:
        if entries:
            fp.write("\n".join(entries) + "\n")


def _normalize_env_path(project: Project, path: str | Path) -> str:
    path = Path(path)
    if not path.is_absolute():
        path = project.root / path
    return os.path.normcase(os.path.abspath(path))


def _format_env_path(project: Project, path: Path) -> str:
    absolute_path = os.path.abspath(path)
    try:
        entry = os.path.relpath(absolute_path, project.root)
    except ValueError:  # Paths on different Windows drives cannot be made relative.
        entry = absolute_path
    if "\n" in entry or "\r" in entry:
        raise PdmUsageError(f"Virtualenv path {entry!r} cannot be represented in .python-envs.")
    return Path(entry).as_posix()


def get_default_env_path(project: Project) -> Path | None:
    """Return the last environment listed in .python-envs."""
    entries = _read_python_envs(project)
    if not entries:
        return None
    path = Path(entries[-1])
    return Path(os.path.abspath(path if path.is_absolute() else project.root / path))


def set_default_env(project: Project, path: Path) -> None:
    """Add an environment and make it the last, selected entry."""
    target = _normalize_env_path(project, path)
    entries = _read_python_envs(project)
    entries = [entry for entry in entries if _normalize_env_path(project, entry) != target]
    entries.append(_format_env_path(project, path))
    _write_python_envs(project, entries)


def pop_default_env(project: Project) -> None:
    """Remove the last environment from .python-envs."""
    python_envs = _get_python_envs_path(project)
    if not python_envs.exists() and not python_envs.is_symlink():
        return
    entries = _read_python_envs(project)
    if entries:
        _write_python_envs(project, entries[:-1])


def clear_envs(project: Project) -> None:
    """Clear the PEP 832 environment listing."""
    python_envs = _get_python_envs_path(project)
    if python_envs.exists() or python_envs.is_symlink():
        _read_python_envs(project)
        _write_python_envs(project, [])


def register_venv(project: Project, venv: Path) -> None:
    """Register a virtualenv without changing the selected environment."""
    target = _normalize_env_path(project, venv)
    if target == _normalize_env_path(project, project.root / ".venv"):
        return
    entries = _read_python_envs(project)
    if any(_normalize_env_path(project, entry) == target for entry in entries):
        return
    entry = _format_env_path(project, venv)
    entries.insert(max(len(entries) - 1, 0), entry)
    _write_python_envs(project, entries)


def unregister_venv(project: Project, venv: Path) -> None:
    """Remove all references to a virtualenv from the PEP 832 listing."""
    python_envs = _get_python_envs_path(project)
    if not python_envs.exists() and not python_envs.is_symlink():
        return
    target = _normalize_env_path(project, venv)
    entries = _read_python_envs(project)
    remaining = [entry for entry in entries if _normalize_env_path(project, entry) != target]
    if remaining != entries:
        _write_python_envs(project, remaining)


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


class VenvProvider(BaseProvider):
    """A Python provider for project venv pythons"""

    def __init__(self, project: Project) -> None:
        self.project = project

    @classmethod
    def create(cls) -> Self | None:
        return None

    def find_pythons(self) -> Iterable[PythonVersion]:
        for _, venv in iter_venvs(self.project):
            yield PythonVersion(venv.interpreter, _interpreter=venv.interpreter, keep_symlink=True)


def get_venv_with_name(project: Project, name: str) -> VirtualEnv:
    all_venvs = dict(iter_venvs(project))
    try:
        return all_venvs[name]
    except KeyError:
        raise PdmUsageError(
            f"No virtualenv with key '{name}' is found, must be one of {list(all_venvs)}.\n"
            "You can create one with 'pdm venv create'.",
        ) from None
