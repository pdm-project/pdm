import argparse
import shutil
from pathlib import Path

from pdm import termui
from pdm.cli.commands.base import BaseCommand
from pdm.cli.commands.venv.utils import get_venv_with_name
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
        venv = get_venv_with_name(project, options.env)
        if options.yes or termui.confirm(f"[warning]Will remove: [success]{venv.root}[/], continue?", default=True):
            shutil.rmtree(venv.root)
            saved_python = project._saved_python
            if saved_python and Path(saved_python).parent.parent == venv.root:
                project._saved_python = None
            project.core.ui.echo("Removed successfully!")
