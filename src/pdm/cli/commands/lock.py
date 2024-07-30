import argparse
import re
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
    override_option,
    skip_option,
)
from pdm.models.markers import EnvSpec
from pdm.models.specifiers import PySpecSet
from pdm.project import Project
from pdm.utils import convert_to_datetime


class Command(BaseCommand):
    """Resolve and lock dependencies"""

    arguments = (
        *BaseCommand.arguments,
        lockfile_option,
        no_isolation_option,
        config_setting_option,
        override_option,
        skip_option,
        groups_group,
        lock_strategy_group,
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--refresh",
            action="store_true",
            help="Refresh the content hash and file hashes in the lock file",
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

        target_group = parser.add_argument_group("Lock Target")
        target_group.add_argument("--python", help="The Python range to lock for. E.g. `>=3.9`, `==3.12.*`")
        target_group.add_argument(
            "--platform",
            help="The platform to lock for. E.g. `windows`, `linux`, `macos`, `manylinux_2_17_x86_64`. "
            "See docs for available choices: http://pdm-project.org/en/latest/usage/lock-targets/",
        )
        target_group.add_argument(
            "--implementation",
            help="The Python implementation to lock for. E.g. `cpython`, `pypy`, `pyston`",
        )
        target_group.add_argument("--append", action="store_true", help="Append the result to the current lock file")

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
        env_spec: EnvSpec | None = None
        if any([options.python, options.platform, options.implementation]):
            replace_dict = {}
            if options.python:
                if re.match(r"[\d.]+", options.python):
                    options.python = f">={options.python}"
                replace_dict["requires_python"] = PySpecSet(options.python)
            if options.platform:
                replace_dict["platform"] = options.platform
            if options.implementation:
                replace_dict["implementation"] = options.implementation
            env_spec = project.environment.allow_all_spec.replace(**replace_dict)

        actions.do_lock(
            project,
            refresh=options.refresh,
            strategy=cast(str, strategy),
            groups=selection.all(),
            strategy_change=options.strategy_change,
            hooks=HookManager(project, options.skip),
            env_spec=env_spec,
            append=options.append,
        )
