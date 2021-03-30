import os
from typing import Any, List, Optional

from pdm.project import Project


def check_fingerprint(project, filename):
    return os.path.basename(filename) == "setup.py"


def convert(project, filename, options):
    raise NotImplementedError()


def export(project: Project, candidates: List, options: Optional[Any]) -> str:
    from pdm.pep517.base import Builder

    builder = Builder(project.root)
    return builder.format_setup_py()
