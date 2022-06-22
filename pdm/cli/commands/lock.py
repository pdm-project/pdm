import argparse

from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.hooks import HookManager
from pdm.cli.options import lockfile_option, no_isolation_option, skip_option
from pdm.project import Project


class Command(BaseCommand):
    """Resolve and lock dependencies"""

    arguments = BaseCommand.arguments + [
        lockfile_option,
        no_isolation_option,
        skip_option,
    ]

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--refresh",
            action="store_true",
            help="Don't update pinned versions, only refresh the lock file",
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        actions.do_lock(
            project,
            refresh=options.refresh,
            hooks=HookManager(project, options.skip),
        )
