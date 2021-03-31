import os
from pathlib import Path
from typing import Any, List, Optional

from pdm.project import Project


def check_fingerprint(project: Project, filename: Path) -> bool:
    return os.path.basename(filename) == "setup.py"


def convert(project: Project, filename: Path, options: Optional[Any]) -> None:
    raise NotImplementedError()


def export(project: Project, candidates: List, options: Optional[Any]) -> str:
    from pdm.pep517.base import Builder

    builder = Builder(project.root)
    return builder.format_setup_py()
