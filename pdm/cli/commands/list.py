import argparse

from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.project import Project


class Command(BaseCommand):
    """List packages installed in the current working set"""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "--graph", action="store_true", help="Display a graph of dependencies"
        )
        group.add_argument(
            "--freeze",
            action="store_true",
            help="Show the installed dependencies in pip's requirements.txt format",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Show the installed dependencies in JSON document format",
        )
        parser.add_argument(
            "-r", "--reverse", action="store_true", help="Reverse the dependency graph"
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        actions.do_list(
            project,
            graph=options.graph,
            reverse=options.reverse,
            freeze=options.freeze,
            json=options.json,
        )
