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

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
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
        actions.do_use(project)
        is_library = click.confirm(
            "Is the project a library that will be upload to PyPI?",
        )
        if is_library:
            name = click.prompt("Project name", default=project.root.name)
            version = click.prompt("Project version", default="0.1.0")
        else:
            name, version = "", ""
        license = click.prompt("License(SPDX name)", default="MIT")

        git_user, git_email = get_user_email_from_git()
        author = click.prompt("Author name", default=git_user)
        email = click.prompt("Author email", default=git_email)
        python_version, _ = get_python_version(project.python_executable, True, 2)
        python_requires = click.prompt(
            "Python requires('*' to allow any)", default=f">={python_version}"
        )

        actions.do_init(project, name, version, license, author, email, python_requires)
        actions.ask_for_import(project)
