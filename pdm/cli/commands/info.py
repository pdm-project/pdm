import argparse

from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import global_option
from pdm.project import Project


class Command(BaseCommand):
    """Show the project information"""

    arguments = [global_option]

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--python", action="store_true", help="Show the interpreter path."
        )
        parser.add_argument(
            "--directory",
            dest="show_project",
            action="store_true",
            help="Show the project root path.",
        )
        parser.add_argument(
            "--env", action="store_true", help="Show PEP508 environment markers."
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        actions.do_info(project, options.python, options.show_project, options.env)
