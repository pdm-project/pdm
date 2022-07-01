import argparse
from pathlib import Path

from pdm.cli.commands.base import BaseCommand
from pdm.cli.commands.venv.utils import iter_venvs
from pdm.cli.options import verbose_option
from pdm.project import Project


class ListCommand(BaseCommand):
    """List all virtualenvs associated with this project"""

    arguments = [verbose_option]

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        project.core.ui.echo("Virtualenvs created with this project:\n")
        for ident, venv in iter_venvs(project):
            saved_python = project.project_config.get("python.path")
            if saved_python and Path(saved_python).parent.parent == venv:
                mark = "*"
            else:
                mark = "-"
            project.core.ui.echo(f"{mark}  [green]{ident}[/]: {venv}")
