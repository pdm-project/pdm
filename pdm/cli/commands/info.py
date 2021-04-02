import argparse
import json

from pdm import termui
from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import ArgumentGroup
from pdm.cli.utils import check_project_file
from pdm.models.in_process import get_python_version
from pdm.project import Project
from pdm.utils import get_python_version_string


class Command(BaseCommand):
    """Show the project information"""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        group = ArgumentGroup("fields", is_mutually_exclusive=True)
        group.add_argument(
            "--python", action="store_true", help="Show the interpreter path"
        )
        group.add_argument(
            "--where",
            dest="where",
            action="store_true",
            help="Show the project root path",
        )
        group.add_argument(
            "--packages", action="store_true", help="Show the packages root"
        )
        group.add_argument(
            "--env", action="store_true", help="Show PEP 508 environment markers"
        )
        group.add_to_parser(parser)

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        check_project_file(project)
        python_path = project.python_executable
        if options.python:
            project.core.ui.echo(python_path)
        elif options.where:
            project.core.ui.echo(project.root.as_posix())
        elif options.packages:
            project.core.ui.echo(str(project.environment.packages_path))
        elif options.env:
            project.core.ui.echo(
                json.dumps(project.environment.marker_environment, indent=2)
            )
        else:
            python_version, is_64bit = get_python_version(python_path, True)

            rows = [
                (termui.cyan("PDM version:", bold=True), project.core.version),
                (
                    termui.cyan("Python Interpreter:", bold=True),
                    python_path
                    + f" ({get_python_version_string(python_version, is_64bit)})",
                ),
                (termui.cyan("Project Root:", bold=True), project.root.as_posix()),
                (
                    termui.cyan("Project Packages:", bold=True),
                    str(project.environment.packages_path),
                ),
            ]
            project.core.ui.display_columns(rows)
