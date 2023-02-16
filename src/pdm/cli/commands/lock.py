import argparse
import sys

from pdm import termui
from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.hooks import HookManager
from pdm.cli.options import lockfile_option, no_isolation_option, skip_option
from pdm.project import Project


class Command(BaseCommand):
    """Resolve and lock dependencies"""

    arguments = [*BaseCommand.arguments, lockfile_option, no_isolation_option, skip_option]

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--refresh",
            action="store_true",
            help="Don't update pinned versions, only refresh the lock file",
        )

        parser.add_argument(
            "--check",
            action="store_true",
            help="Check if the lock file is up to date and quit",
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        if options.check:
            strategy = actions.check_lockfile(project, False)
            if strategy:
                project.core.ui.echo(
                    f"[error]{termui.Emoji.FAIL}[/] Lockfile is [error]out of date[/].",
                    err=True,
                    verbosity=termui.Verbosity.DETAIL,
                )
                sys.exit(1)
            else:
                project.core.ui.echo(
                    f"[success]{termui.Emoji.SUCC}[/] Lockfile is [success]up to date[/].",
                    err=True,
                    verbosity=termui.Verbosity.DETAIL,
                )
                sys.exit(0)

        actions.do_lock(
            project,
            refresh=options.refresh,
            hooks=HookManager(project, options.skip),
        )
