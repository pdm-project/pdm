import argparse
import shutil
from pathlib import Path

from pdm import termui
from pdm.cli.commands.base import BaseCommand
from pdm.cli.commands.venv.utils import iter_venvs
from pdm.cli.options import verbose_option
from pdm.project import Project


class RemoveCommand(BaseCommand):
    """Remove the virtualenv with the given name"""

    arguments = [verbose_option]

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-y",
            "--yes",
            action="store_true",
            help="Answer yes on the following question",
        )
        parser.add_argument("env", help="The key of the virtualenv")

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        project.core.ui.echo("Virtualenvs created with this project:")
        for ident, venv in iter_venvs(project):
            if ident == options.env:
                if options.yes or termui.confirm(f"[warning]Will remove: [success]{venv}[/], continue?", default=True):
                    shutil.rmtree(venv)
                    saved_python = project._saved_python
                    if saved_python and Path(saved_python).parent.parent == venv:
                        project._saved_python = None
                    project.core.ui.echo("Removed successfully!")
                break
        else:
            project.core.ui.echo(
                f"No virtualenv with key [success]{options.env}[/] is found",
                style="warning",
                err=True,
            )
            raise SystemExit(1)
