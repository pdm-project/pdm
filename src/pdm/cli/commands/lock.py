import argparse
import sys
from typing import cast

from pdm import termui
from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.filters import GroupSelection
from pdm.cli.hooks import HookManager
from pdm.cli.options import (
    config_setting_option,
    groups_group,
    lock_strategy_group,
    lockfile_option,
    no_isolation_option,
    skip_option,
)
from pdm.project import Project
from pdm.utils import convert_to_datetime


class Command(BaseCommand):
    """Resolve and lock dependencies"""

    arguments = (
        *BaseCommand.arguments,
        lockfile_option,
        no_isolation_option,
        config_setting_option,
        skip_option,
        groups_group,
        lock_strategy_group,
    )

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
            "--update-reuse",
            action="store_const",
            dest="update_strategy",
            default="all",
            const="reuse",
            help="Reuse pinned versions already present in lock file if possible",
        )
        parser.add_argument(
            "--update-reuse-installed",
            action="store_const",
            dest="update_strategy",
            const="reuse-installed",
            help="Reuse installed packages if possible",
        )
        parser.add_argument(
            "--exclude-newer",
            help="Exclude packages newer than the given UTC date in format `YYYY-MM-DD[THH:MM:SSZ]`",
            type=convert_to_datetime,
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
        strategy = options.update_strategy
        if options.exclude_newer:
            strategy = "all"
            if strategy != options.update_strategy:
                project.core.ui.info("--exclue-newer is set, forcing --update-all")
        project.core.state.exclude_newer = options.exclude_newer
        actions.do_lock(
            project,
            refresh=options.refresh,
            strategy=cast(str, strategy),
            groups=selection.all(),
            strategy_change=options.strategy_change,
            hooks=HookManager(project, options.skip),
        )
