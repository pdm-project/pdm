from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Any

from pdm import termui
from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.hooks import HookManager
from pdm.cli.options import skip_option
from pdm.cli.templates import ProjectTemplate
from pdm.models.backends import _BACKENDS, DEFAULT_BACKEND, BuildBackend, get_backend
from pdm.models.python import PythonInfo
from pdm.models.specifiers import get_specifier
from pdm.models.venv import get_venv_python
from pdm.utils import get_user_email_from_git

if TYPE_CHECKING:
    from pdm.project import Project


class Command(BaseCommand):
    """Initialize a pyproject.toml for PDM"""

    def __init__(self) -> None:
        self.interactive = True

    def do_init(
        self, project: Project, metadata: dict[str, Any], hooks: HookManager, options: argparse.Namespace
    ) -> None:
        """Bootstrap the project and create a pyproject.toml"""
        with ProjectTemplate(options.template) as template:
            template.generate(project.root, metadata)
        project.pyproject.reload()
        hooks.try_emit("post_init")

    def set_interactive(self, value: bool) -> None:
        self.interactive = value

    def ask(self, question: str, default: str) -> str:
        if not self.interactive:
            return default
        return termui.ask(question, default=default)

    def get_metadata_from_input(self, project: Project, options: argparse.Namespace) -> dict[str, Any]:
        from pdm.formats.base import array_of_inline_tables, make_array, make_inline_table

        is_library = options.lib
        if not is_library and self.interactive:
            is_library = termui.confirm(
                "Is the project a library that is installable?\n"
                "If yes, we will need to ask a few more questions to include "
                "the project name and build backend"
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
                    default=0,
                )
                build_backend = get_backend(all_backends[int(selected_backend)])
            else:
                build_backend = DEFAULT_BACKEND
        else:
            name, version, description = "", "", ""
        license = self.ask("License(SPDX name)", "MIT")

        git_user, git_email = get_user_email_from_git()
        author = self.ask("Author name", git_user)
        email = self.ask("Author email", git_email)
        python = project.python
        python_version = f"{python.major}.{python.minor}"
        python_requires = self.ask("Python requires('*' to allow any)", f">={python_version}")

        data = {
            "project": {
                "name": name,
                "version": version,
                "description": description,
                "authors": array_of_inline_tables([{"name": author, "email": email}]),
                "license": make_inline_table({"text": license}),
                "dependencies": make_array([], True),
            },
        }

        if python_requires and python_requires != "*":
            get_specifier(python_requires)
            data["project"]["requires-python"] = python_requires
        if build_backend is not None:
            data["build-system"] = build_backend.build_system()

        return data

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
        parser.add_argument("--lib", action="store_true", help="Create a library project")
        parser.add_argument(
            "template", nargs="?", help="Specify the project template, which can be a local path or a Git URL"
        )
        parser.set_defaults(search_parent=False)

    def set_python(self, project: Project, python: str | None, hooks: HookManager) -> None:
        from pdm.cli.commands.use import Command as UseCommand

        do_use = UseCommand().do_use
        if self.interactive:
            python_info = do_use(
                project,
                python or "",
                first=bool(python),
                ignore_remembered=True,
                ignore_requires_python=True,
                save=False,
                hooks=hooks,
            )
        else:
            python_info = do_use(
                project,
                python or "3",
                first=True,
                ignore_remembered=True,
                ignore_requires_python=True,
                save=False,
                hooks=hooks,
            )
        if project.config["python.use_venv"] and python_info.get_venv() is None:
            if not self.interactive or termui.confirm(
                f"Would you like to create a virtualenv with [success]{python_info.executable}[/]?",
                default=True,
            ):
                project._python = python_info
                try:
                    path = project._create_virtualenv()
                    python_info = PythonInfo.from_path(get_venv_python(path))
                except Exception as e:  # pragma: no cover
                    project.core.ui.echo(
                        f"Error occurred when creating virtualenv: {e}\nPlease fix it and create later.",
                        style="error",
                        err=True,
                    )
        if python_info.get_venv() is None:
            project.core.ui.echo(
                "You are using the PEP 582 mode, no virtualenv is created.\n"
                "For more info, please visit https://peps.python.org/pep-0582/",
                style="success",
            )
        project.python = python_info

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        hooks = HookManager(project, options.skip)
        if project.pyproject.exists():
            project.core.ui.echo("pyproject.toml already exists, update it now.", style="primary")
        else:
            project.core.ui.echo("Creating a pyproject.toml for PDM...", style="primary")
        self.set_interactive(not options.non_interactive)

        self.set_python(project, options.python, hooks)

        metadata = self.get_metadata_from_input(project, options)
        self.do_init(project, metadata, hooks=hooks, options=options)
        project.core.ui.echo("Project is initialized successfully", style="primary")
        if self.interactive:
            actions.ask_for_import(project)
