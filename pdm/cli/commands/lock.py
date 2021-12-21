import argparse

from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import no_isolation_option
from pdm.project import Project


class Command(BaseCommand):
    """Resolve and lock dependencies"""

    arguments = BaseCommand.arguments + [no_isolation_option]

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--refresh",
            action="store_true",
            help="Don't update pinned versions, only refresh the lock file",
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        actions.do_lock(project, refresh=options.refresh)
