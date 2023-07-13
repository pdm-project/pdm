import argparse
import sys

from pdm import termui
from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.filters import GroupSelection
from pdm.cli.hooks import HookManager
from pdm.cli.options import (
    groups_group,
    lockfile_option,
    no_isolation_option,
    skip_option,
)
from pdm.project import Project


class Command(BaseCommand):
    """Resolve and lock dependencies"""

    arguments = (*BaseCommand.arguments, lockfile_option, no_isolation_option, skip_option, groups_group)

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
        parser.add_argument(
            "--no-cross-platform",
            action="store_false",
            default=True,
            dest="cross_platform",
            help="Only lock packages for the current platform",
        )
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "--static-urls", action="store_true", help="Store static file URLs in the lockfile", default=None
        )
        group.add_argument(
            "--no-static-urls",
            action="store_false",
            dest="static_urls",
            help="Do not store static file URLs in the lockfile",
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
        selection = GroupSelection.from_options(project, options)
        actions.do_lock(
            project,
            refresh=options.refresh,
            groups=selection.all(),
            cross_platform=options.cross_platform,
            static_urls=options.static_urls,
            hooks=HookManager(project, options.skip),
        )
