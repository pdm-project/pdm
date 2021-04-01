import argparse

from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import packages_group, save_strategy_group, update_strategy_group
from pdm.project import Project


class Command(BaseCommand):
    """Add package(s) to pyproject.toml and install them"""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-d",
            "--dev",
            default=False,
            action="store_true",
            help="Add packages into dev dependencies",
        )
        parser.add_argument(
            "-s", "--section", help="Specify target section to add into"
        )
        parser.add_argument(
            "--no-sync",
            dest="sync",
            default=True,
            action="store_false",
            help="Only write pyproject.toml and do not sync the working set",
        )
        save_strategy_group.add_to_parser(parser)
        update_strategy_group.add_to_parser(parser)
        packages_group.add_to_parser(parser)

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        actions.do_add(
            project,
            dev=options.dev,
            section=options.section,
            sync=options.sync,
            save=options.save_strategy or project.config["strategy.save"],
            strategy=options.update_strategy or project.config["strategy.update"],
            editables=options.editables,
            packages=options.packages,
        )
