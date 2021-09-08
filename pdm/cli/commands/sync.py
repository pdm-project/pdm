import argparse

from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import (
    clean_group,
    dry_run_option,
    groups_group,
    install_group,
    no_isolation_option,
)
from pdm.project import Project


class Command(BaseCommand):
    """Synchronize the current working set with lock file"""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        groups_group.add_to_parser(parser)
        dry_run_option.add_to_parser(parser)
        parser.add_argument(
            "-r",
            "--reinstall",
            action="store_true",
            help="Force reinstall existing dependencies",
        )
        no_isolation_option.add_to_parser(parser)
        clean_group.add_to_parser(parser)
        install_group.add_to_parser(parser)

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        if options.build_isolation is not None:
            project.environment.build_isolation = options.build_isolation
        actions.do_sync(
            project,
            groups=options.groups,
            dev=options.dev,
            default=options.default,
            dry_run=options.dry_run,
            clean=options.clean,
            no_editable=options.no_editable,
            no_self=options.no_self,
            reinstall=options.reinstall,
        )
