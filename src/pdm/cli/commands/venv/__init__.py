from __future__ import annotations

import argparse
from pathlib import Path
from pdm.cli.commands.venv.utils import get_venv_with_name, iter_venvs, get_venv_python

from pdm.exceptions import PdmUsageError
from pdm.project import Project
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
    arguments: list[Option] = []

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--path", help="Show the path to the given virtualenv")
        parser.add_argument("--python", help="Show the python interpreter path for the given virtualenv")
        subparser = parser.add_subparsers()
        CreateCommand.register_to(subparser, "create")
        ListCommand.register_to(subparser, "list")
        RemoveCommand.register_to(subparser, "remove")
        ActivateCommand.register_to(subparser, "activate")
        PurgeCommand.register_to(subparser, "purge")
        self.parser = parser

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        if options.path and options.python:
            raise PdmUsageError("--path and --python are mutually exclusive")
        if options.path:
            venv = get_venv_with_name(project, options.path)
            project.core.ui.echo(str(venv))
        elif options.python:
            venv = get_venv_with_name(project, options.python)
            project.core.ui.echo(str(get_venv_python(venv)))
        else:
            self.parser.print_help()
