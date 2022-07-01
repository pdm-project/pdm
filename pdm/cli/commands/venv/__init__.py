import argparse
from typing import List

from pdm import Project
from pdm.cli.commands.base import BaseCommand
from pdm.cli.commands.venv.activate import ActivateCommand
from pdm.cli.commands.venv.create import CreateCommand
from pdm.cli.commands.venv.list import ListCommand
from pdm.cli.commands.venv.purge import PurgeCommand
from pdm.cli.commands.venv.remove import RemoveCommand
from pdm.cli.options import Option


class Command(BaseCommand):
    """Virtualenv management"""

    name = "venv"
    arguments: List[Option] = []

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        subparser = parser.add_subparsers()
        CreateCommand.register_to(subparser, "create")
        ListCommand.register_to(subparser, "list")
        RemoveCommand.register_to(subparser, "remove")
        ActivateCommand.register_to(subparser, "activate")
        PurgeCommand.register_to(subparser, "purge")
        self.parser = parser

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        self.parser.print_help()
