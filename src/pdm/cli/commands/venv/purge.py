import argparse
import shutil
from pathlib import Path

from pdm import termui
from pdm.cli.commands.base import BaseCommand
from pdm.cli.commands.venv.utils import iter_central_venvs
from pdm.cli.options import verbose_option
from pdm.project import Project


class PurgeCommand(BaseCommand):
    """Purge selected/all created Virtualenvs"""

    arguments = (verbose_option,)

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-f",
            "--force",
            action="store_true",
            help="Force purging without prompting for confirmation",
        )
        parser.add_argument(
            "-i",
            "--interactive",
            action="store_true",
            help="Interactively purge selected Virtualenvs",
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        all_central_venvs = list(iter_central_venvs(project))
        if not all_central_venvs:
            project.core.ui.echo("No virtualenvs to purge, quitting.", style="success")
            return

        if not options.force:
            project.core.ui.echo("The following Virtualenvs will be purged:", style="warning")
            for i, venv in enumerate(all_central_venvs):
                project.core.ui.echo(f"{i}. [success]{venv[0]}[/]")

        if not options.interactive:
            if options.force or termui.confirm("continue?", default=True):
                return self.del_all_venvs(project)

        selection = termui.ask(
            "Please select",
            choices=([str(i) for i in range(len(all_central_venvs))] + ["all", "none"]),
            default="none",
            show_choices=False,
        )

        if selection == "all":
            self.del_all_venvs(project)
        elif selection != "none":
            for i, venv in enumerate(all_central_venvs):
                if i == int(selection):
                    shutil.rmtree(venv[1])
            project.core.ui.echo("Purged successfully!")

    def del_all_venvs(self, project: Project) -> None:
        saved_python = project._saved_python
        for _, venv in iter_central_venvs(project):
            shutil.rmtree(venv)
            if saved_python and Path(saved_python).parent.parent == venv:
                project._saved_python = None
        project.core.ui.echo("Purged successfully!")
