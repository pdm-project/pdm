import argparse

from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.filters import GroupSelection
from pdm.cli.hooks import HookManager
from pdm.cli.options import dry_run_option, install_group, lockfile_option, skip_option
from pdm.project import Project


class Command(BaseCommand):
    """Remove packages from pyproject.toml"""

    arguments = [*BaseCommand.arguments, install_group, dry_run_option, lockfile_option, skip_option]

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-d",
            "--dev",
            default=False,
            action="store_true",
            help="Remove packages from dev dependencies",
        )
        parser.add_argument("-G", "--group", help="Specify the target dependency group to remove from")
        parser.add_argument(
            "--no-sync",
            dest="sync",
            default=True,
            action="store_false",
            help="Only write pyproject.toml and do not uninstall packages",
        )
        parser.add_argument("packages", nargs="+", help="Specify the packages to remove")

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        actions.do_remove(
            project,
            selection=GroupSelection.from_options(project, options),
            sync=options.sync,
            packages=options.packages,
            no_editable=options.no_editable,
            no_self=options.no_self,
            dry_run=options.dry_run,
            fail_fast=options.fail_fast,
            hooks=HookManager(project, options.skip),
        )
