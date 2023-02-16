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
            "-d",
            "--dev",
            default=False,
            action="store_true",
            help="import packages into dev dependencies",
        )
        parser.add_argument("-G", "--group", help="Specify the target dependency group to import into")
        parser.add_argument(
            "-f",
            "--format",
            choices=FORMATS.keys(),
            help="Specify the file format explicitly",
        )
        parser.add_argument("filename", help="The file name")
        parser.set_defaults(search_parent=False)

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        do_import(project, options.filename, options.format, options)
