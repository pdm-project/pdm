import argparse

from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.filters import GroupSelection
from pdm.cli.hooks import HookManager
from pdm.cli.options import (
    clean_group,
    dry_run_option,
    groups_group,
    install_group,
    lockfile_option,
    skip_option,
    venv_option,
)
from pdm.project import Project


class Command(BaseCommand):
    """Synchronize the current working set with lock file"""

    arguments = (
        *BaseCommand.arguments,
        groups_group,
        dry_run_option,
        lockfile_option,
        skip_option,
        clean_group,
        install_group,
        venv_option,
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-r",
            "--reinstall",
            action="store_true",
            help="Force reinstall existing dependencies",
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        actions.check_lockfile(project)
        selection = GroupSelection.from_options(project, options)
        actions.do_sync(
            project,
            selection=selection,
            dry_run=options.dry_run,
            clean=options.clean,
            no_editable=options.no_editable,
            no_self=options.no_self or "default" not in selection,
            reinstall=options.reinstall,
            only_keep=options.only_keep,
            hooks=HookManager(project, options.skip),
        )
