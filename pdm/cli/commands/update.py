import argparse

from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import save_strategy_group, sections_group, update_strategy_group
from pdm.project import Project


class Command(BaseCommand):
    """Update package(s) in pyproject.toml"""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        sections_group.add_to_parser(parser)
        save_strategy_group.add_to_parser(parser)
        update_strategy_group.add_to_parser(parser)
        parser.add_argument(
            "-u",
            "--unconstrained",
            action="store_true",
            default=False,
            help="Ignore the version constraint of packages",
        )
        parser.add_argument(
            "-t",
            "--top",
            action="store_true",
            help="Only update those list in pyproject.toml",
        )
        parser.add_argument(
            "--dry-run",
            "--outdated",
            action="store_true",
            dest="dry_run",
            help="Show the difference only without modifying the lockfile content",
        )
        parser.add_argument(
            "packages", nargs="*", help="If packages are given, only update them"
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        actions.do_update(
            project,
            dev=options.dev,
            sections=options.sections,
            default=options.default,
            save=options.save_strategy or project.config["strategy.save"],
            strategy=options.update_strategy or project.config["strategy.update"],
            unconstrained=options.unconstrained,
            top=options.top,
            dry_run=options.dry_run,
            packages=options.packages,
        )
