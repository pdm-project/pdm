import argparse

from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.project import Project


class Command(BaseCommand):
    """Resolve and lock dependencies"""

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        actions.do_lock(project)
