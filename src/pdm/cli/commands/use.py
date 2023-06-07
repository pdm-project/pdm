from __future__ import annotations

import argparse

from pdm import termui
from pdm.cli.commands.base import BaseCommand
from pdm.cli.hooks import HookManager
from pdm.cli.options import skip_option
from pdm.exceptions import NoPythonVersion
from pdm.models.caches import JSONFileCache
from pdm.models.python import PythonInfo
from pdm.project import Project


class Command(BaseCommand):
    """Use the given python version or path as base interpreter"""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        skip_option.add_to_parser(parser)
        parser.add_argument(
            "-f",
            "--first",
            action="store_true",
            help="Select the first matched interpreter",
        )
        parser.add_argument(
            "-i",
            "--ignore-remembered",
            action="store_true",
            help="Ignore the remembered selection",
        )
        parser.add_argument("--venv", help="Use the interpreter in the virtual environment with the given name")
        parser.add_argument("python", nargs="?", help="Specify the Python version or path", default="")

    @staticmethod
    def select_python(
        project: Project,
        python: str,
        *,
        ignore_remembered: bool,
        ignore_requires_python: bool,
        venv: str | None,
        first: bool,
    ) -> PythonInfo:
        from pdm.cli.commands.venv.utils import get_venv_with_name

        def version_matcher(py_version: PythonInfo) -> bool:
            return py_version.valid and (
                ignore_requires_python or project.python_requires.contains(str(py_version.version), True)
            )

        if venv:
            virtualenv = get_venv_with_name(project, venv)
            return PythonInfo.from_path(virtualenv.interpreter)

        if not project.cache_dir.exists():
            project.cache_dir.mkdir(parents=True)
        use_cache: JSONFileCache[str, str] = JSONFileCache(project.cache_dir / "use_cache.json")
        python = python.strip()
        if python and not ignore_remembered and python in use_cache:
            path = use_cache.get(python)
            cached_python = PythonInfo.from_path(path)
            if not cached_python.valid:
                project.core.ui.echo(
                    f"The last selection is corrupted. {path!r}",
                    style="error",
                    err=True,
                )
            elif version_matcher(cached_python):
                project.core.ui.echo(
                    "Using the last selection, add '-i' to ignore it.",
                    style="warning",
                    err=True,
                )
                return cached_python

        found_interpreters = list(dict.fromkeys(project.find_interpreters(python)))
        matching_interpreters = list(filter(version_matcher, found_interpreters))
        if not found_interpreters:
            raise NoPythonVersion(f"No Python interpreter matching [success]{python}[/] is found.")
        if not matching_interpreters:
            project.core.ui.echo("Interpreters found but not matching:", err=True)
            for py in found_interpreters:
                info = py.identifier if py.valid else "Invalid"
                project.core.ui.echo(f"  - {py.path} ({info})", err=True)
            raise NoPythonVersion(
                f"No python is found meeting the requirement [success]python {project.python_requires!s}[/]"
            )
        if first or len(matching_interpreters) == 1:
            return matching_interpreters[0]

        project.core.ui.echo("Please enter the Python interpreter to use")
        for i, py_version in enumerate(matching_interpreters):
            project.core.ui.echo(f"{i}. [success]{py_version.path!s}[/] ({py_version.identifier})")
        selection = termui.ask(
            "Please select",
            default="0",
            prompt_type=int,
            choices=[str(i) for i in range(len(matching_interpreters))],
            show_choices=False,
        )
        return matching_interpreters[int(selection)]

    def do_use(
        self,
        project: Project,
        python: str = "",
        first: bool = False,
        ignore_remembered: bool = False,
        ignore_requires_python: bool = False,
        save: bool = True,
        venv: str | None = None,
        hooks: HookManager | None = None,
    ) -> PythonInfo:
        """Use the specified python version and save in project config.
        The python can be a version string or interpreter path.
        """
        from pdm.environments.local import PythonLocalEnvironment

        selected_python = self.select_python(
            project,
            python,
            ignore_remembered=ignore_remembered,
            first=first,
            venv=venv,
            ignore_requires_python=ignore_requires_python,
        )
        if python:
            use_cache: JSONFileCache[str, str] = JSONFileCache(project.cache_dir / "use_cache.json")
            use_cache.set(python, selected_python.path.as_posix())

        if not save:
            return selected_python

        saved_python = project._saved_python
        old_python = PythonInfo.from_path(saved_python) if saved_python else None
        project.core.ui.echo(
            f"Using Python interpreter: [success]{selected_python.path!s}[/] ({selected_python.identifier})"
        )
        project.python = selected_python
        if project.environment.is_local:
            project.core.ui.echo(
                "Using __pypackages__ because non-venv Python is used.",
                style="primary",
                err=True,
            )
        if (
            old_python
            and old_python.executable != selected_python.executable
            and isinstance(project.environment, PythonLocalEnvironment)
        ):
            project.core.ui.echo("Updating executable scripts...", style="primary")
            project.environment.update_shebangs(selected_python.executable.as_posix())

        hooks = hooks or HookManager(project)
        hooks.try_emit("post_use", python=selected_python)
        return selected_python

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        self.do_use(
            project,
            python=options.python,
            first=options.first,
            ignore_remembered=options.ignore_remembered,
            venv=options.venv,
            hooks=HookManager(project, options.skip),
        )
