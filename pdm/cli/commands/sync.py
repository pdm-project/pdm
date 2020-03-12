import argparse

from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import clean_group, dry_run_option, sections_group
from pdm.project import Project


class Command(BaseCommand):
    """Synchronize the current working set with lock file"""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        sections_group.add_to_parser(parser)
        dry_run_option.add_to_parser(parser)
        clean_group.add_to_parser(parser)

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        actions.do_sync(
            project,
            sections=options.sections,
            dev=options.dev,
            default=options.default,
            dry_run=options.dry_run,
            clean=options.clean,
        )
