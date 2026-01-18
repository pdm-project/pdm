from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pdm.cli.commands.base import BaseCommand
from pdm.cli.commands.venv.utils import iter_venvs
from pdm.cli.options import verbose_option

if TYPE_CHECKING:
    from argparse import Namespace

    from pdm.project import Project


class ListCommand(BaseCommand):
    """List all virtualenvs associated with this project"""

    arguments = (verbose_option,)

    def handle(self, project: Project, options: Namespace) -> None:
        project.core.ui.echo("Virtualenvs created with this project:\n")
        saved_python_root = Path(saved_python).parent.parent if (saved_python := project._saved_python) else None
        for ident, venv in iter_venvs(project):
            mark = "*" if saved_python_root and saved_python_root == venv.root else "-"
            project.core.ui.echo(f"{mark}  [success]{ident}[/]: {venv.root}")
