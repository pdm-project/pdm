import argparse

from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.hooks import HookManager
from pdm.cli.options import (
    groups_group,
    install_group,
    lockfile_option,
    prerelease_option,
    save_strategy_group,
    skip_option,
    unconstrained_option,
    update_strategy_group,
)
from pdm.project import Project


class Command(BaseCommand):
    """Update package(s) in pyproject.toml"""

    arguments = [
        *BaseCommand.arguments,
        groups_group,
        install_group,
        lockfile_option,
        save_strategy_group,
        update_strategy_group,
        prerelease_option,
        unconstrained_option,
        skip_option,
    ]

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-t",
            "--top",
            action="store_true",
            help="Only update those listed in pyproject.toml",
        )
        parser.add_argument(
            "--dry-run",
            "--outdated",
            action="store_true",
            dest="dry_run",
            help="Show the difference only without modifying the lockfile content",
        )
        parser.add_argument(
            "--no-sync",
            dest="sync",
            default=True,
            action="store_false",
            help="Only update lock file but do not sync packages",
        )
        parser.add_argument("packages", nargs="*", help="If packages are given, only update them")
        parser.set_defaults(dev=None)

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        actions.do_update(
            project,
            dev=options.dev,
            groups=options.groups,
            default=options.default,
            save=options.save_strategy or project.config["strategy.save"],
            strategy=options.update_strategy or project.config["strategy.update"],
            unconstrained=options.unconstrained,
            top=options.top,
            dry_run=options.dry_run,
            packages=options.packages,
            sync=options.sync,
            no_editable=options.no_editable,
            no_self=options.no_self,
            prerelease=options.prerelease,
            hooks=HookManager(project, options.skip),
        )
