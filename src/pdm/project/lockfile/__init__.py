from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from pdm.project.lockfile.base import (
    FLAG_CROSS_PLATFORM,
    FLAG_DIRECT_MINIMAL_VERSIONS,
    FLAG_INHERIT_METADATA,
    FLAG_STATIC_URLS,
    Lockfile,
)
from pdm.project.lockfile.pdmlock import PDMLock
from pdm.project.lockfile.pylock import PyLock

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


if TYPE_CHECKING:
    from pdm.project import Project

__all__ = [
    "FLAG_CROSS_PLATFORM",
    "FLAG_DIRECT_MINIMAL_VERSIONS",
    "FLAG_INHERIT_METADATA",
    "FLAG_STATIC_URLS",
    "Lockfile",
    "PDMLock",
    "PyLock",
    "load_lockfile",
]


def load_lockfile(project: Project, path: str | Path) -> Lockfile:
    """Load a lockfile from the given path."""

    default_lockfile = PyLock if project.config["lock.format"] == "pylock" else PDMLock

    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except OSError:
        return default_lockfile(path, ui=project.core.ui)
    else:
        if data.get("metadata", {}).get("lock_version"):
            return PDMLock(path, ui=project.core.ui)
        elif data.get("lock-version"):
            return PyLock(path, ui=project.core.ui)
        else:  # pragma: no cover
            return default_lockfile(path, ui=project.core.ui)
