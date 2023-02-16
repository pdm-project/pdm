import argparse
import json

from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import ArgumentGroup
from pdm.cli.utils import check_project_file
from pdm.project import Project


class Command(BaseCommand):
    """Show the project information"""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        group = ArgumentGroup("fields", is_mutually_exclusive=True)
        group.add_argument("--python", action="store_true", help="Show the interpreter path")
        group.add_argument(
            "--where",
            dest="where",
            action="store_true",
            help="Show the project root path",
        )
        group.add_argument("--packages", action="store_true", help="Show the packages root")
        group.add_argument("--env", action="store_true", help="Show PEP 508 environment markers")
        group.add_to_parser(parser)

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        check_project_file(project)
        interpreter = project.python
        if options.python:
            project.core.ui.echo(str(interpreter.executable))
        elif options.where:
            project.core.ui.echo(str(project.root))
        elif options.packages:
            project.core.ui.echo(str(project.environment.packages_path))
        elif options.env:
            project.core.ui.echo(json.dumps(project.environment.marker_environment, indent=2))
        else:
            for name, value in zip(
                [
                    f"[primary]{key}[/]:"
                    for key in [
                        "PDM version",
                        "Python Interpreter",
                        "Project Root",
                        "Project Packages",
                    ]
                ],
                [
                    project.core.version,
                    f"{interpreter.executable} ({interpreter.identifier})",
                    project.root.as_posix(),
                    str(project.environment.packages_path),
                ],
            ):
                project.core.ui.echo(f"{name}\n  {value}")
