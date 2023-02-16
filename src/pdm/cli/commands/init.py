from __future__ import annotations

import argparse

from pdm import termui
from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.hooks import HookManager
from pdm.cli.options import skip_option
from pdm.models.backends import _BACKENDS, BuildBackend, get_backend
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
        parser.add_argument("--python", help="Specify the Python version/path to use")
        parser.add_argument("--backend", choices=list(_BACKENDS), help="Specify the build backend")
        parser.set_defaults(search_parent=False)

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        from pdm.cli.commands.venv.utils import get_venv_python

        hooks = HookManager(project, options.skip)
        if project.pyproject.exists:
            project.core.ui.echo("pyproject.toml already exists, update it now.", style="primary")
        else:
            project.core.ui.echo("Creating a pyproject.toml for PDM...", style="primary")
        self.set_interactive(not options.non_interactive)

        if self.interactive:
            python = actions.do_use(
                project,
                options.python or "",
                first=bool(options.python),
                ignore_remembered=True,
                ignore_requires_python=True,
                hooks=hooks,
            )
            if project.config["python.use_venv"] and get_venv_like_prefix(python.executable) is None:
                if termui.confirm(
                    f"Would you like to create a virtualenv with [success]{python.executable}[/]?",
                    default=True,
                ):
                    try:
                        path = project._create_virtualenv()
                        python = project.python = PythonInfo.from_path(get_venv_python(path))
                    except Exception as e:  # pragma: no cover
                        project.core.ui.echo(
                            f"Error occurred when creating virtualenv: {e}\nPlease fix it and create later.",
                            style="error",
                            err=True,
                        )
        else:
            python = actions.do_use(
                project,
                options.python or "3",
                first=True,
                ignore_remembered=True,
                ignore_requires_python=True,
                save=False,
                hooks=hooks,
            )
        if get_venv_like_prefix(python.executable) is None:
            project.core.ui.echo(
                "You are using the PEP 582 mode, no virtualenv is created.\n"
                "For more info, please visit https://peps.python.org/pep-0582/",
                style="success",
            )
        is_library = (
            termui.confirm(
                "Is the project a library that is installable?\n"
                "A few more questions will be asked to include a project name "
                "and build backend"
            )
            if self.interactive
            else False
        )
        build_backend: type[BuildBackend] | None = None
        if is_library:
            name = self.ask("Project name", project.root.name)
            version = self.ask("Project version", "0.1.0")
            description = self.ask("Project description", "")
            if options.backend:
                build_backend = get_backend(options.backend)
            elif self.interactive:
                all_backends = list(_BACKENDS)
                project.core.ui.echo("Which build backend to use?")
                for i, backend in enumerate(all_backends):
                    project.core.ui.echo(f"{i}. [success]{backend}[/]")
                selected_backend = termui.ask(
                    "Please select",
                    prompt_type=int,
                    choices=[str(i) for i in range(len(all_backends))],
                    show_choices=False,
                    default=all_backends.index("pdm-pep517"),
                )
                build_backend = get_backend(all_backends[int(selected_backend)])
            else:
                build_backend = get_backend("pdm-pep517")
        else:
            name, version, description = "", "", ""
        license = self.ask("License(SPDX name)", "MIT")

        git_user, git_email = get_user_email_from_git()
        author = self.ask("Author name", git_user)
        email = self.ask("Author email", git_email)
        python_version = f"{python.major}.{python.minor}"
        python_requires = self.ask("Python requires('*' to allow any)", f">={python_version}")

        actions.do_init(
            project,
            name=name,
            version=version,
            description=description,
            license=license,
            author=author,
            email=email,
            python_requires=python_requires,
            build_backend=build_backend,
            hooks=hooks,
        )
        if self.interactive:
            actions.ask_for_import(project)
