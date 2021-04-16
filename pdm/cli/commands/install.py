import argparse
import sys

import click

from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import sections_group
from pdm.cli.utils import compatible_dev_flag
from pdm.project import Project


class Command(BaseCommand):
    """Install dependencies from lock file"""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        sections_group.add_to_parser(parser)
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
            if not project.lockfile_file.exists():
                project.core.ui.echo(
                    "Lock file does not exist, trying to generate one..."
                )
                actions.do_lock(project, strategy="all")
            elif not project.is_lockfile_hash_match():
                project.core.ui.echo(
                    "Lock file hash doesn't match pyproject.toml, regenerating..."
                )
                actions.do_lock(project, strategy="reuse")
        actions.do_sync(
            project,
            sections=options.sections,
            dev=compatible_dev_flag(project, options.dev),
            default=options.default,
        )
