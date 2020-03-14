import argparse
import subprocess
import sys

from pdm.cli.commands.base import BaseCommand
from pdm.exceptions import PdmUsageError
from pdm.iostream import stream
from pdm.project import Project


class Command(BaseCommand):
    """Run commands or scripts with local packages loaded"""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("command", help="The command to run")
        parser.add_argument(
            "args",
            nargs=argparse.REMAINDER,
            help="Arguments that will be passed to the command",
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        with project.environment.activate():
            expanded_command = project.environment.which(options.command)
            if not expanded_command:
                raise PdmUsageError(
                    "Command {} is not found on your PATH.".format(
                        stream.green(f"'{options.command}'")
                    )
                )
            sys.exit(subprocess.call([expanded_command] + list(options.args)))
