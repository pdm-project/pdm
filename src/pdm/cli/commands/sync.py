import argparse

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
    """Install selected locked packages without updating the lockfile"""

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
        parser.epilog = (
            "Reads group selections from pyproject.toml without changing it. Requires an existing lockfile and "
            "installs its pinned versions for the selected groups. Does not resolve new versions or update the "
            "lockfile. Keeps unrelated installed packages by default. --clean removes packages absent from the "
            "whole lockfile; --clean-unselected also removes packages outside the selected groups."
        )
        parser.add_argument(
            "-r",
            "--reinstall",
            action="store_true",
            help="Force reinstall existing dependencies",
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        from pdm.cli import actions

        actions.check_lockfile(project)
        selection = GroupSelection.from_options(project, options)
        actions.do_sync(
            project,
            selection=selection,
            dry_run=options.dry_run,
            clean=options.clean,
            quiet=options.verbose == -1,
            no_editable=options.no_editable,
            no_self=options.no_self or "default" not in selection,
            reinstall=options.reinstall,
            only_keep=options.only_keep,
            hooks=HookManager(project, options.skip),
        )
