from __future__ import annotations

import argparse

from pdm.cli.commands.base import BaseCommand
from pdm.cli.commands.venv.activate import ActivateCommand
from pdm.cli.commands.venv.create import CreateCommand
from pdm.cli.commands.venv.list import ListCommand
from pdm.cli.commands.venv.purge import PurgeCommand
from pdm.cli.commands.venv.remove import RemoveCommand
from pdm.cli.commands.venv.utils import get_venv_with_name
from pdm.cli.options import project_option
from pdm.project import Project


class Command(BaseCommand):
    """Virtualenv management"""

    name = "venv"
    arguments = (project_option,)

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        group = parser.add_mutually_exclusive_group()
        group.add_argument("--path", help="Show the path to the given virtualenv")
        group.add_argument("--python", help="Show the python interpreter path for the given virtualenv")
        subparser = parser.add_subparsers(metavar="venv", title="commands")
        CreateCommand.register_to(subparser, "create")
        ListCommand.register_to(subparser, "list")
        RemoveCommand.register_to(subparser, "remove")
        ActivateCommand.register_to(subparser, "activate")
        PurgeCommand.register_to(subparser, "purge")
        self.parser = parser

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        if options.path:
            venv = get_venv_with_name(project, options.path)
            project.core.ui.echo(str(venv.root))
        elif options.python:
            venv = get_venv_with_name(project, options.python)
            project.core.ui.echo(str(venv.interpreter))
        else:
            self.parser.print_help()
