import argparse

from pdm import signals
from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.commands.run import run_script_if_present
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


signals.pre_lock.connect(run_script_if_present("pre_lock"), weak=False)
signals.post_lock.connect(run_script_if_present("post_lock"), weak=False)
