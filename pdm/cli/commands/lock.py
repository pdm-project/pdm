import argparse

from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import no_isolation_option
from pdm.project import Project


class Command(BaseCommand):
    """Resolve and lock dependencies"""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        no_isolation_option.add_to_parser(parser)

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        actions.do_lock(project)
