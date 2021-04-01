import argparse

import click

from pdm import termui
from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.models.in_process import get_python_version
from pdm.project import Project
from pdm.utils import get_user_email_from_git


class Command(BaseCommand):
    """Initialize a pyproject.toml for PDM"""

    @staticmethod
    def ask(question: str, default: str, use_default: bool = False) -> str:
        if use_default:
            return default
        return click.prompt(question, default=default)

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-n",
            "--non-interactive",
            action="store_true",
            help="Don't ask questions but use default values",
        )
        parser.set_defaults(search_parent=False)

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        if project.pyproject_file.exists():
            project.core.ui.echo(
                "{}".format(
                    termui.cyan("pyproject.toml already exists, update it now.")
                )
            )
        else:
            project.core.ui.echo(
                "{}".format(termui.cyan("Creating a pyproject.toml for PDM..."))
            )
        non_interactive = options.non_interactive
        if non_interactive:
            actions.do_use(project, "3", True)
        else:
            actions.do_use(project)
        is_library = (
            False
            if non_interactive
            else click.confirm(
                "Is the project a library that will be upload to PyPI?",
            )
        )
        if is_library:
            name = self.ask("Project name", project.root.name, non_interactive)
            version = self.ask("Project version", "0.1.0", non_interactive)
        else:
            name, version = "", ""
        license = self.ask("License(SPDX name)", "MIT", non_interactive)

        git_user, git_email = get_user_email_from_git()
        author = self.ask("Author name", git_user, non_interactive)
        email = self.ask("Author email", git_email, non_interactive)
        python_version, _ = get_python_version(project.python_executable, True, 2)
        python_requires = self.ask(
            "Python requires('*' to allow any)", f">={python_version}", non_interactive
        )

        actions.do_init(project, name, version, license, author, email, python_requires)
        if not non_interactive:
            actions.ask_for_import(project)
