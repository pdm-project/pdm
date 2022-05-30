import argparse

from pdm import signals, termui
from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.commands.run import run_script_if_present
from pdm.project import Project
from pdm.utils import get_user_email_from_git


class Command(BaseCommand):
    """Initialize a pyproject.toml for PDM"""

    def __init__(self, parser: argparse.ArgumentParser) -> None:
        super().__init__(parser)
        self.interactive = True

    def set_interactive(self, value: bool) -> None:
        self.interactive = value

    def ask(self, question: str, default: str) -> str:
        if not self.interactive:
            return default
        return termui.ask(question, default=default)

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
                "pyproject.toml already exists, update it now.", style="cyan"
            )
        else:
            project.core.ui.echo("Creating a pyproject.toml for PDM...", style="cyan")
        self.set_interactive(not options.non_interactive)

        if self.interactive:
            actions.do_use(project)
        else:
            actions.do_use(project, "3", True)
        is_library = (
            termui.confirm(
                "Is the project a library that will be uploaded to PyPI", default=False
            )
            if self.interactive
            else False
        )
        if is_library:
            name = self.ask("Project name", project.root.name)
            version = self.ask("Project version", "0.1.0")
            description = self.ask("Project description", "")
        else:
            name, version, description = "", "", ""
        license = self.ask("License(SPDX name)", "MIT")

        git_user, git_email = get_user_email_from_git()
        author = self.ask("Author name", git_user)
        email = self.ask("Author email", git_email)
        python_version = f"{project.python.major}.{project.python.minor}"
        python_requires = self.ask(
            "Python requires('*' to allow any)", f">={python_version}"
        )

        actions.do_init(
            project,
            name=name,
            version=version,
            description=description,
            license=license,
            author=author,
            email=email,
            python_requires=python_requires,
        )
        if self.interactive:
            actions.ask_for_import(project)


signals.post_init.connect(run_script_if_present("post_init"), weak=False)
