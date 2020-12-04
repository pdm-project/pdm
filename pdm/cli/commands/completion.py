import argparse

from pdm.cli.commands.base import BaseCommand
from pdm.iostream import stream
from pdm.project import Project


class Command(BaseCommand):
    """Generate completion scripts for the given shell"""

    arguments = []

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "shell",
            nargs="?",
            help="The shell to generate the scripts for. "
            "If not given, PDM will properly guess from `SHELL` env var.",
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        import shellingham
        from pycomplete import Completer

        completer = Completer(project.core.parser)
        stream.echo(completer.render(options.shell or shellingham.detect_shell()[0]))
