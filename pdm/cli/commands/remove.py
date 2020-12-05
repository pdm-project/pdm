import argparse

from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.project import Project


class Command(BaseCommand):
    """Remove packages from pyproject.toml"""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-d",
            "--dev",
            default=False,
            action="store_true",
            help="Remove packages from dev dependencies",
        )
        parser.add_argument(
            "-s", "--section", help="Specify the section the package belongs to"
        )
        parser.add_argument(
            "--no-sync",
            dest="sync",
            default=True,
            action="store_false",
            help="Only write pyproject.toml and do not uninstall packages",
        )
        parser.add_argument(
            "packages", nargs="+", help="Specify the packages to remove"
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        actions.do_remove(
            project,
            dev=options.dev,
            section=options.section,
            sync=options.sync,
            packages=options.packages,
        )
