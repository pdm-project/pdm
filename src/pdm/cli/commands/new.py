import argparse
import os

from pdm.cli.commands.base import verbose_option
from pdm.cli.commands.init import Command as InitCommand
from pdm.project.core import Project


class Command(InitCommand):
    """Create a new Python project at <project_path>"""

    arguments = (verbose_option,)

    def add_arguments(self, parser: argparse.ArgumentParser, is_init=False) -> None:
        super().add_arguments(parser, is_init=is_init)
        parser.add_argument("project_path", help="The path to create the new project")

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        new_project = project.core.create_project(
            options.project_path, global_config=options.config or os.getenv("PDM_CONFIG_FILE")
        )
        return super().handle(new_project, options)
