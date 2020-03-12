import argparse

from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.project import Project


class Command(BaseCommand):
    """List packages installed in the current working set"""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--graph", action="store_true", help="Display a graph of dependencies"
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        actions.do_list(project, options.graph)
