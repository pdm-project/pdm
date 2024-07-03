import argparse
import json

from rich import print_json

from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import ArgumentGroup, venv_option
from pdm.cli.utils import check_project_file
from pdm.project import Project


class Command(BaseCommand):
    """Show the project information"""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        venv_option.add_to_parser(parser)
        group = ArgumentGroup("fields", is_mutually_exclusive=True)
        group.add_argument("--python", action="store_true", help="Show the interpreter path")
        group.add_argument(
            "--where",
            dest="where",
            action="store_true",
            help="Show the project root path",
        )
        group.add_argument("--packages", action="store_true", help="Show the local packages root")
        group.add_argument("--env", action="store_true", help="Show PEP 508 environment markers")
        group.add_argument("--json", action="store_true", help="Dump the information in JSON")
        group.add_to_parser(parser)

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        check_project_file(project)
        interpreter = project.environment.interpreter
        packages_path = ""
        if project.environment.is_local:
            packages_path = project.environment.packages_path  # type: ignore[attr-defined]
        if options.python:
            project.core.ui.echo(str(interpreter.executable))
        elif options.where:
            project.core.ui.echo(str(project.root))
        elif options.packages:
            project.core.ui.echo(str(packages_path))
        elif options.env:
            project.core.ui.echo(json.dumps(project.environment.spec.markers_with_defaults(), indent=2))
        elif options.json:
            print_json(
                data={
                    "pdm": {"version": project.core.version},
                    "python": {
                        "interpreter": str(interpreter.executable),
                        "version": interpreter.identifier,
                        "markers": project.environment.spec.markers_with_defaults(),
                    },
                    "project": {
                        "root": str(project.root),
                        "pypackages": str(packages_path),
                    },
                }
            )
        else:
            for name, value in zip(
                [
                    f"[primary]{key}[/]:"
                    for key in [
                        "PDM version",
                        f"{'Global ' if project.is_global else ''}Python Interpreter",
                        f"{'Global ' if project.is_global else ''}Project Root",
                        f"{'Global ' if project.is_global else ''}Local Packages",
                    ]
                ],
                [
                    project.core.version,
                    f"{interpreter.executable} ({interpreter.identifier})",
                    project.root.as_posix(),
                    str(packages_path),
                ],
            ):
                project.core.ui.echo(f"{name}\n  {value}")
