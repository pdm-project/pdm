import argparse

from pdm import termui
from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.hooks import HookManager
from pdm.cli.options import skip_option
from pdm.models.python import PythonInfo
from pdm.project import Project
from pdm.utils import get_user_email_from_git, get_venv_like_prefix


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
        skip_option.add_to_parser(parser)
        parser.add_argument(
            "-n",
            "--non-interactive",
            action="store_true",
            help="Don't ask questions but use default values",
        )
        parser.set_defaults(search_parent=False)

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        from pdm.cli.commands.venv.utils import get_venv_python

        hooks = HookManager(project, options.skip)
        if project.pyproject_file.exists():
            project.core.ui.echo(
                "pyproject.toml already exists, update it now.", style="cyan"
            )
        else:
            project.core.ui.echo("Creating a pyproject.toml for PDM...", style="cyan")
        self.set_interactive(not options.non_interactive)

        if self.interactive:
            python = actions.do_use(project, ignore_requires_python=True, hooks=hooks)
            if (
                project.config["python.use_venv"]
                and get_venv_like_prefix(python.executable) is None
            ):
                if termui.confirm(
                    "Would you like to create a virtualenv with "
                    f"[green]{python.executable}[/]?",
                    default=True,
                ):
                    try:
                        path = project._create_virtualenv()
                        project.python = PythonInfo.from_path(get_venv_python(path))
                    except Exception as e:  # pragma: no cover
                        project.core.ui.echo(
                            f"Error occurred when creating virtualenv: {e}\n"
                            "Please fix it and create later.",
                            style="red",
                            err=True,
                        )
        else:
            actions.do_use(project, "3", True, ignore_requires_python=True, hooks=hooks)
        if get_venv_like_prefix(project.python.executable) is None:
            project.core.ui.echo(
                "You are using the PEP 582 mode, no virtualenv is created.\n"
                "For more info, please visit https://peps.python.org/pep-0582/",
                style="green",
            )
        is_library = (
            termui.confirm("Is the project a library that will be uploaded to PyPI")
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
            hooks=hooks,
        )
        if self.interactive:
            actions.ask_for_import(project)
