from __future__ import annotations

import argparse

from pdm import termui
from pdm.cli.commands.base import BaseCommand
from pdm.cli.hooks import HookManager
from pdm.cli.options import skip_option
from pdm.exceptions import NoPythonVersion
from pdm.models.caches import JSONFileCache
from pdm.models.python import PythonInfo
from pdm.models.venv import get_venv_python
from pdm.project import Project
from pdm.utils import is_conda_base_python


class Command(BaseCommand):
    """Use the given python version or path as base interpreter. If not found, PDM will try to install one."""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        skip_option.add_to_parser(parser)
        unattended_use_group = parser.add_mutually_exclusive_group()
        unattended_use_group.add_argument(
            "-f",
            "--first",
            action="store_true",
            help="Select the first matched interpreter - no auto install",
        )
        unattended_use_group.add_argument(
            "--auto-install-min",
            action="store_true",
            help="If `python` argument not given, auto install minimal best match - otherwise has no effect",
        )
        unattended_use_group.add_argument(
            "--auto-install-max",
            action="store_true",
            help="If `python` argument not given, auto install maximum best match - otherwise has no effect",
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
        auto_install_min: bool,
        auto_install_max: bool,
    ) -> PythonInfo:
        from pdm.cli.commands.python import InstallCommand
        from pdm.cli.commands.venv.utils import get_venv_with_name

        def version_matcher(py_version: PythonInfo) -> bool:
            return py_version.valid and (
                ignore_requires_python or project.python_requires.contains(py_version.version, True)
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
                project.core.ui.error(
                    f"The last selection is corrupted. {path!r}",
                )
            elif version_matcher(cached_python):
                project.core.ui.info("Using the last selection, add '-i' to ignore it.")
                return cached_python

        if not python and not first and (auto_install_min or auto_install_max):
            match = project.get_best_matching_cpython_version(auto_install_min)
            if match is None:
                req = f'requires-python="{project.python_requires}"'
                raise NoPythonVersion(
                    f"No Python interpreter matching [success]{req}[/] is found based on 'auto-install' strategy."
                )
            try:
                installed_interpreter_to_use = InstallCommand.install_python(project, str(match))
            except Exception as e:
                project.core.ui.error(f"Failed to install Python {python}: {e}")
                project.core.ui.info("Please select a Python interpreter manually")
            else:
                return installed_interpreter_to_use

        found_interpreters = list(dict.fromkeys(project.iter_interpreters(python, filter_func=version_matcher)))
        if not found_interpreters:
            req = python if ignore_requires_python else f'requires-python="{project.python_requires}"'
            raise NoPythonVersion(f"No Python interpreter matching [success]{req}[/] is found.")

        if first or len(found_interpreters) == 1 or not termui.is_interactive():
            project.core.ui.info("Using the first matched interpreter.")
            return found_interpreters[0]

        project.core.ui.echo(
            f"Please enter the {'[bold]Global[/] ' if project.is_global else ''}Python interpreter to use"
        )
        for i, py_version in enumerate(found_interpreters):
            project.core.ui.echo(
                f"{i:>2}. [success]{py_version.implementation}@{py_version.identifier}[/] ({py_version.path!s})"
            )
        selection = termui.ask(
            "Please select",
            default="0",
            prompt_type=int,
            choices=[str(i) for i in range(len(found_interpreters))],
            show_choices=False,
        )
        return found_interpreters[int(selection)]

    def do_use(
        self,
        project: Project,
        python: str = "",
        first: bool = False,
        ignore_remembered: bool = False,
        ignore_requires_python: bool = False,
        save: bool = True,
        venv: str | None = None,
        auto_install_min: bool = False,
        auto_install_max: bool = False,
        hooks: HookManager | None = None,
    ) -> PythonInfo:
        """Use the specified python version and save in project config.
        The python can be a version string or interpreter path.
        """
        from pdm.environments import PythonLocalEnvironment

        selected_python = self.select_python(
            project,
            python,
            ignore_remembered=ignore_remembered,
            first=first,
            venv=venv,
            ignore_requires_python=ignore_requires_python,
            auto_install_min=auto_install_min,
            auto_install_max=auto_install_max,
        )
        # NOTE: PythonInfo is cached with path as key.
        # This can lead to inconsistency when the same virtual environment is reused.
        # So the original python identifier is preserved here for logging purpose.
        selected_python_identifier = selected_python.identifier
        if python:
            use_cache: JSONFileCache[str, str] = JSONFileCache(project.cache_dir / "use_cache.json")
            use_cache.set(python, selected_python.path.as_posix())

        if project.config["python.use_venv"] and (
            selected_python.get_venv() is None or is_conda_base_python(selected_python.path)
        ):
            venv_path = project._create_virtualenv(str(selected_python.path))
            selected_python = PythonInfo.from_path(get_venv_python(venv_path))
        if not save:
            return selected_python

        saved_python = project._saved_python
        old_python = PythonInfo.from_path(saved_python) if saved_python else None
        project.core.ui.echo(
            f"Using {'[bold]Global[/] ' if project.is_global else ''}Python interpreter: [success]{selected_python.path!s}[/] ({selected_python_identifier})"
        )
        project.python = selected_python
        if project.environment.is_local:
            assert isinstance(project.environment, PythonLocalEnvironment)
            project.core.ui.echo(
                "Using __pypackages__ because non-venv Python is used.",
                style="primary",
                err=True,
            )
            if old_python and old_python.executable != selected_python.executable:
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
            auto_install_min=options.auto_install_min,
            auto_install_max=options.auto_install_max,
            hooks=HookManager(project, options.skip),
        )
