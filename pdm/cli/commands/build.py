import argparse

from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import project_option, verbose_option
from pdm.project import Project


class Command(BaseCommand):
    """Build artifacts for distribution"""

    arguments = [verbose_option, project_option]

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--no-sdist",
            dest="sdist",
            default=True,
            action="store_false",
            help="Don't build source tarballs",
        )
        parser.add_argument(
            "--no-wheel",
            dest="wheel",
            default=True,
            action="store_false",
            help="Don't build wheels",
        )
        parser.add_argument(
            "-d", "--dest", default="dist", help="Target directory to put artifacts"
        )
        parser.add_argument(
            "--no-clean",
            dest="clean",
            default=True,
            action="store_false",
            help="Do not clean the target directory",
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        actions.do_build(
            project, options.sdist, options.wheel, options.dest, options.clean
        )
