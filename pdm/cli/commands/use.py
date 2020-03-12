import argparse

from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.project import Project


class Command(BaseCommand):
    """Use the given python version or path as base interpreter"""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-f",
            "--first",
            action="store_true",
            help="Select the first matched interpreter",
        )
        parser.add_argument("python", help="Specify the Python version or path")

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        actions.do_use(project, options.python, options.first)
