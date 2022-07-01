import argparse
import shutil
from pathlib import Path

from pdm import Project, termui
from pdm.cli.commands.base import BaseCommand
from pdm.cli.commands.venv.utils import iter_venvs
from pdm.cli.options import verbose_option


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
                if options.yes or termui.confirm(
                    f"[yellow]Will remove: [green]{venv}[/], continue?"
                ):
                    shutil.rmtree(venv)
                    if (
                        project.project_config.get("python.path")
                        and Path(project.project_config["python.path"]).parent.parent
                        == venv
                    ):
                        del project.project_config["python.path"]
                    project.core.ui.echo("Removed successfully!")
                break
        else:
            project.core.ui.echo(
                f"No virtualenv with key [green]{options.env}[/] is found",
                style="yellow",
                err=True,
            )
            raise SystemExit(1)
