import argparse

from pdm.cli.actions import do_import
from pdm.cli.commands.base import BaseCommand
from pdm.formats import FORMATS
from pdm.project import Project


class Command(BaseCommand):
    """Import project metadata from other formats"""

    name = "import"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-f",
            "--format",
            choices=FORMATS.keys(),
            help="Specify the file format explicitly",
        )
        parser.add_argument("filename", help="The file name")
        parser.set_defaults(project=self.project_class("."))

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        do_import(project, options.filename, options.format)
