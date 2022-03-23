from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
from typing import Any, Callable, Mapping, NamedTuple, Sequence, cast

from pdm import termui
from pdm._types import TypedDict
from pdm.cli.actions import PEP582_PATH
from pdm.cli.commands.base import BaseCommand
from pdm.cli.utils import check_project_file
from pdm.exceptions import PdmUsageError
from pdm.project import Project
from pdm.utils import is_path_relative_to


class TaskOptions(TypedDict, total=False):
    env: Mapping[str, str]
    env_file: str | None
    help: str
    site_packages: bool


class Task(NamedTuple):
    kind: str
    name: str
    args: str | Sequence[str]
    options: TaskOptions

    def __str__(self) -> str:
        return f"<task {termui.cyan(self.name)}>"


class TaskRunner:
    """The task runner for pdm project"""

    TYPES = ["cmd", "shell", "call"]
    OPTIONS = ["env", "env_file", "help", "site_packages"]

    def __init__(self, project: Project) -> None:
        self.project = project
        global_options = cast(
            TaskOptions,
            self.project.scripts.get("_", {}) if self.project.scripts else {},
        )
        self.global_options = global_options.copy()

    def _get_task(self, script_name: str) -> Task | None:
        if script_name not in self.project.scripts:
            return None
        script = cast(
            "str | Sequence[str] | Mapping[str,Any]", self.project.scripts[script_name]
        )
        if not isinstance(script, Mapping):
            # Regard as the same as {cmd = ... }
            kind = "cmd"
            value = script
            options = {}
        else:
            script = dict(script)  # to remove the effect of tomlkit's container type.
            for key in self.TYPES:
                if key in script:
                    kind = key
                    value = cast("str | Sequence[str]", script.pop(key))
                    break
            else:
                raise PdmUsageError(
                    f"Script type must be one of ({', '.join(self.TYPES)})"
                )
            options = script.copy()
        unknown_options = set(options) - set(self.OPTIONS)
        if unknown_options:
            raise PdmUsageError(
                f"Unknown options for task {script_name}: {', '.join(unknown_options)}"
            )
        return Task(kind, script_name, value, cast(TaskOptions, options))

    def _run_process(
        self,
        args: Sequence[str] | str,
        chdir: bool = False,
        shell: bool = False,
        site_packages: bool = False,
        env: Mapping[str, str] | None = None,
        env_file: str | None = None,
    ) -> int:
        """Run command in a subprocess and return the exit code."""
        project = self.project
        process_env = os.environ.copy()
        if "PYTHONPATH" in process_env:
            pythonpath = os.pathsep.join([PEP582_PATH, os.getenv("PYTHONPATH", "")])
        else:
            pythonpath = PEP582_PATH
        project_env = project.environment
        this_path = project_env.get_paths()["scripts"]
        python_root = os.path.dirname(project.python.executable)
        new_path = os.pathsep.join([this_path, os.getenv("PATH", ""), python_root])
        process_env.update(
            {
                "PYTHONPATH": pythonpath,
                "PATH": new_path,
                "PDM_PROJECT_ROOT": str(project.root),
            }
        )
        if project_env.packages_path:
            process_env.update({"PEP582_PACKAGES": str(project_env.packages_path)})
        if env_file:
            import dotenv

            project.core.ui.echo(
                f"Loading .env file: {termui.green(env_file)}",
                err=True,
                verbosity=termui.DETAIL,
            )
            process_env.update(
                dotenv.dotenv_values(project.root / env_file, encoding="utf-8")
            )
        if env:
            process_env.update(env)
        if shell:
            assert isinstance(args, str)
            expanded_args: str | Sequence[str] = os.path.expandvars(args)
        else:
            assert isinstance(args, Sequence)
            command, *args = args
            expanded_command = project_env.which(command)
            if not expanded_command:
                raise PdmUsageError(
                    "Command {} is not found on your PATH.".format(
                        termui.green(f"'{command}'")
                    )
                )
            expanded_command = os.path.expanduser(os.path.expandvars(expanded_command))
            expanded_args = [
                os.path.expandvars(arg) for arg in [expanded_command] + args
            ]
            if (
                not project_env.is_global
                and not site_packages
                and (
                    command.startswith("python")
                    or is_path_relative_to(expanded_command, this_path)
                )
            ):
                # The executable belongs to the local packages directory.
                # Don't load system site-packages
                process_env["NO_SITE_PACKAGES"] = "1"

        cwd = project.root if chdir else None
        process = subprocess.Popen(expanded_args, cwd=cwd, env=process_env, shell=shell)
        try:
            process.wait()
        except KeyboardInterrupt:
            pass
        return process.returncode

    def _run_task(self, task: Task, args: Sequence[str] = ()) -> int:
        kind, _, value, options = task
        options.pop("help", None)
        shell = False
        if kind == "cmd":
            if not isinstance(value, list):
                value = shlex.split(str(value))
            args = value + list(args)
        elif kind == "shell":
            assert isinstance(value, str)
            args = " ".join([value] + list(args))  # type: ignore
            shell = True
        elif kind == "call":
            assert isinstance(value, str)
            module, _, func = value.partition(":")
            if not module or not func:
                raise PdmUsageError(
                    "Python callable must be in the form <module_name>:<callable_name>"
                )
            short_name = "_1"
            if re.search(r"\(.*?\)", func) is None:
                func += "()"
            args = [
                "python",
                "-c",
                f"import sys, {module} as {short_name};"
                f"sys.exit({short_name}.{func})",
            ] + list(args)
        if "env" in self.global_options:
            options["env"] = {**self.global_options["env"], **options.get("env", {})}
        options["env_file"] = options.get(
            "env_file", self.global_options.get("env_file")
        )
        self.project.core.ui.echo(
            f"Running {task}: {termui.green(str(args))}",
            err=True,
            verbosity=termui.DETAIL,
        )
        return self._run_process(
            args, chdir=True, shell=shell, **options  # type: ignore
        )

    def run(self, command: str, args: Sequence[str]) -> int:
        task = self._get_task(command)
        if task is not None:
            pre_task = self._get_task(f"pre_{command}")
            if pre_task is not None:
                code = self._run_task(pre_task)
                if code != 0:
                    return code
            code = self._run_task(task, args)
            if code != 0:
                return code
            post_task = self._get_task(f"post_{command}")
            if post_task is not None:
                code = self._run_task(post_task)
            return code
        else:
            return self._run_process(
                [command] + args, **self.global_options  # type: ignore
            )

    def show_list(self) -> None:
        if not self.project.scripts:
            return
        columns = ["Name", "Type", "Script", "Description"]
        result = []
        for name in self.project.scripts:
            if name == "_":
                continue
            task = self._get_task(name)
            assert task is not None
            result.append(
                (
                    termui.green(name),
                    task.kind,
                    str(task.args),
                    task.options.get("help", ""),
                )
            )
        self.project.core.ui.display_columns(result, columns)


class Command(BaseCommand):
    """Run commands or scripts with local packages loaded"""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-l",
            "--list",
            action="store_true",
            help="Show all available scripts defined in pyproject.toml",
        )
        parser.add_argument(
            "-s",
            "--site-packages",
            action="store_true",
            help="Load site-packages from the selected interpreter",
        )
        parser.add_argument("command", nargs="?", help="The command to run")
        parser.add_argument(
            "args",
            nargs=argparse.REMAINDER,
            help="Arguments that will be passed to the command",
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        check_project_file(project)
        runner = TaskRunner(project)
        if options.list:
            return runner.show_list()
        if options.site_packages:
            runner.global_options.update({"site_packages": options.site_packages})
        if not options.command:
            project.core.ui.echo(
                "No command is given, default to the Python REPL.",
                fg="yellow",
                err=True,
            )
            options.command = "python"
        sys.exit(runner.run(options.command, options.args))


def run_script_if_present(script_name: str) -> Callable:
    """Helper to create a signal handler to run specific script"""

    def handler(sender: Project, **kwargs: Any) -> None:
        runner = TaskRunner(sender)
        task = runner._get_task(script_name)
        if task is None:
            return
        exit_code = runner._run_task(task)
        if exit_code != 0:
            sys.exit(exit_code)

    return handler
