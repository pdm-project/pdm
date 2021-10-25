import argparse
import sys

import click

from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import dry_run_option, groups_group, install_group
from pdm.project import Project


class Command(BaseCommand):
    """Install dependencies from lock file"""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        groups_group.add_to_parser(parser)
        install_group.add_to_parser(parser)
        dry_run_option.add_to_parser(parser)
        parser.add_argument(
            "--no-lock",
            dest="lock",
            action="store_false",
            default=True,
            help="Don't do lock if lockfile is not found or outdated.",
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        if not project.meta and click._compat.isatty(sys.stdout):
            actions.ask_for_import(project)

        if options.lock:
            if not (
                project.lockfile_file.exists() and project.is_lockfile_compatible()
            ):
                project.core.ui.echo(
                    "Lock file does not exist or is incompatible, "
                    "trying to generate one..."
                )
                actions.do_lock(project, strategy="all", dry_run=options.dry_run)
            elif not project.is_lockfile_hash_match():
                project.core.ui.echo(
                    "Lock file hash doesn't match pyproject.toml, regenerating..."
                )
                actions.do_lock(project, strategy="reuse", dry_run=options.dry_run)

        actions.do_sync(
            project,
            groups=options.groups,
            dev=options.dev,
            default=options.default,
            no_editable=options.no_editable,
            no_self=options.no_self,
            dry_run=options.dry_run,
        )
