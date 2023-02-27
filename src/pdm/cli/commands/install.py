import argparse
import sys

from pdm import termui
from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.filters import GroupSelection
from pdm.cli.hooks import HookManager
from pdm.cli.options import (
    dry_run_option,
    groups_group,
    install_group,
    lockfile_option,
    skip_option,
)
from pdm.project import Project


class Command(BaseCommand):
    """Install dependencies from lock file"""

    arguments = [*BaseCommand.arguments, groups_group, install_group, dry_run_option, lockfile_option, skip_option]

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--no-lock",
            dest="lock",
            action="store_false",
            default=True,
            help="Don't do lock if the lock file is not found or outdated",
        )
        parser.add_argument(
            "--check",
            action="store_true",
            help="Check if the lock file is up to date and fail otherwise",
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        if not project.pyproject.is_valid and termui.is_interactive():
            actions.ask_for_import(project)

        hooks = HookManager(project, options.skip)

        strategy = actions.check_lockfile(project, False)
        selection = GroupSelection.from_options(project, options)
        if strategy:
            if options.check:
                project.core.ui.echo(
                    "Please run [success]`pdm lock`[/] to update the lock file",
                    err=True,
                )
                sys.exit(1)
            if options.lock:
                project.core.ui.echo("Updating the lock file...", style="success", err=True)

                actions.do_lock(
                    project, strategy=strategy, dry_run=options.dry_run, hooks=hooks, groups=selection.all()
                )

        actions.do_sync(
            project,
            selection=selection,
            no_editable=options.no_editable,
            no_self=options.no_self,
            dry_run=options.dry_run,
            fail_fast=options.fail_fast,
            hooks=hooks,
        )
