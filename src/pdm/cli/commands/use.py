import argparse

from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.hooks import HookManager
from pdm.cli.options import skip_option
from pdm.project import Project


class Command(BaseCommand):
    """Use the given python version or path as base interpreter"""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        skip_option.add_to_parser(parser)
        parser.add_argument(
            "-f",
            "--first",
            action="store_true",
            help="Select the first matched interpreter",
        )
        parser.add_argument(
            "-i",
            "--ignore-remembered",
            action="store_true",
            help="Ignore the remembered selection",
        )
        parser.add_argument("python", nargs="?", help="Specify the Python version or path", default="")

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        actions.do_use(
            project,
            python=options.python,
            first=options.first,
            ignore_remembered=options.ignore_remembered,
            hooks=HookManager(project, options.skip),
        )
