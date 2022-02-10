import argparse
import sys

import click

from pdm import signals
from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.commands.run import run_script_if_present
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
            help="Don't do lock if the lock file is not found or outdated",
        )
        parser.add_argument(
            "--check",
            action="store_true",
            help="Check if the lock file is up to date and fail otherwise",
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        if not project.meta and click._compat.isatty(sys.stdout):
            actions.ask_for_import(project)

        strategy = actions.check_lockfile(project, False)
        if strategy:
            if options.check:
                project.core.ui.echo(
                    "Please run `pdm lock` to update the lock file", err=True
                )
                sys.exit(1)
            if options.lock:
                project.core.ui.echo("Updating the lock file...", fg="green", err=True)
                actions.do_lock(project, strategy=strategy, dry_run=options.dry_run)

        actions.do_sync(
            project,
            groups=options.groups,
            dev=options.dev,
            default=options.default,
            no_editable=options.no_editable,
            no_self=options.no_self,
            dry_run=options.dry_run,
        )


signals.pre_install.connect(run_script_if_present("pre_install"), weak=False)
signals.post_install.connect(run_script_if_present("post_install"), weak=False)
