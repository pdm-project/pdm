from __future__ import annotations

import argparse
import itertools
import os
import re
import shlex
import signal
import subprocess
import sys
from pathlib import Path
from types import FrameType
from typing import TYPE_CHECKING, Mapping, NamedTuple, Sequence, cast

from rich import print_json

from pdm import termui
from pdm.cli.commands.base import BaseCommand
from pdm.cli.hooks import HookManager
from pdm.cli.options import skip_option, venv_option
from pdm.cli.utils import check_project_file
from pdm.exceptions import PdmUsageError
from pdm.project import Project
from pdm.signals import pdm_signals
from pdm.utils import is_path_relative_to

if TYPE_CHECKING:
    from typing import Any, Callable, Iterator, TypedDict

    class EnvFileOptions(TypedDict, total=True):
        override: str

    class TaskOptions(TypedDict, total=False):
        env: Mapping[str, str]
        env_file: EnvFileOptions | str | None
        help: str
        site_packages: bool


def exec_opts(*options: TaskOptions | None) -> dict[str, Any]:
    return dict(
        env={k: v for opts in options if opts for k, v in opts.get("env", {}).items()},
        **{k: v for opts in options if opts for k, v in opts.items() if k not in ("env", "help")},
    )


RE_ARGS_PLACEHOLDER = re.compile(r"{args(?::(?P<default>[^}]*))?}")
RE_PDM_PLACEHOLDER = re.compile(r"{pdm}")


def _interpolate_args(script: str, args: Sequence[str]) -> tuple[str, bool]:
    """Interpolate the `{args:[defaults]} placeholder in a string"""
    import shlex

    def replace(m: re.Match[str]) -> str:
        default = m.group("default") or ""
        return shlex.join(args) if args else default

    interpolated, count = RE_ARGS_PLACEHOLDER.subn(replace, script)
    return interpolated, count > 0


def _interpolate_pdm(script: str) -> str:
    """Interpolate the `{pdm} placeholder in a string"""
    executable_path = Path(sys.executable)

    def replace(m: re.Match[str]) -> str:
        return shlex.join([executable_path.as_posix(), "-m", "pdm"])

    interpolated = RE_PDM_PLACEHOLDER.sub(replace, script)
    return interpolated


def interpolate(script: str, args: Sequence[str]) -> tuple[str, bool]:
    """Interpolate the `{args:[defaults]} placeholder in a string"""

    script, args_interpolated = _interpolate_args(script, args)
    script = _interpolate_pdm(script)
    return script, args_interpolated


class Task(NamedTuple):
    kind: str
    name: str
    args: str | Sequence[str]
    options: TaskOptions

    def __str__(self) -> str:
        return f"<task [primary]{self.name}[/]>"

    @property
    def short_description(self) -> str:
        """
        A short one line task description
        """
        if self.kind == "composite":
            fallback = f" {termui.Emoji.ARROW_SEPARATOR} ".join(self.args)
        else:
            lines = [line.strip() for line in str(self.args).splitlines() if line.strip()]
            fallback = f"{lines[0]}{termui.Emoji.ELLIPSIS}" if len(lines) > 1 else lines[0]
        return self.options.get("help", fallback)


class TaskRunner:
    """The task runner for pdm project"""

    TYPES = ("cmd", "shell", "call", "composite")
    OPTIONS = ("env", "env_file", "help", "site_packages")

    def __init__(self, project: Project, hooks: HookManager) -> None:
        self.project = project
        global_options = cast(
            "TaskOptions",
            self.project.scripts.get("_", {}) if self.project.scripts else {},
        )
        self.global_options = global_options.copy()
        self.hooks = hooks

    def get_task(self, script_name: str) -> Task | None:
        if script_name not in self.project.scripts:
            return None
        script = cast("str | Sequence[str] | Mapping[str,Any]", self.project.scripts[script_name])
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
                raise PdmUsageError(f"Script type must be one of ({', '.join(self.TYPES)})")
            options = script.copy()
        unknown_options = set(options) - set(self.OPTIONS)
        if unknown_options:
            raise PdmUsageError(f"Unknown options for task {script_name}: {', '.join(unknown_options)}")
        return Task(kind, script_name, value, cast("TaskOptions", options))

    def expand_command(self, command: str) -> str:
        expanded_command = os.path.expanduser(os.path.expandvars(command))
        if expanded_command.replace(os.sep, "/").startswith(("./", "../")):
            abspath = os.path.abspath(expanded_command)
            if not os.path.isfile(abspath):
                raise PdmUsageError(f"Command [success]'{command}'[/] is not a valid executable.")
            return abspath
        result = self.project.environment.which(command)
        if not result:
            raise PdmUsageError(f"Command [success]'{command}'[/] is not found in your PATH.")
        return result

    def _run_process(
        self,
        args: Sequence[str] | str,
        chdir: bool = False,
        shell: bool = False,
        site_packages: bool = False,
        env: Mapping[str, str] | None = None,
        env_file: EnvFileOptions | str | None = None,
    ) -> int:
        """Run command in a subprocess and return the exit code."""
        project = self.project
        process_env = os.environ.copy()
        if env_file is not None:
            if isinstance(env_file, str):
                path = env_file
                override = False
            else:
                path = env_file["override"]
                override = True

            import dotenv

            project.core.ui.echo(
                f"Loading .env file: [success]{env_file}[/]",
                err=True,
                verbosity=termui.Verbosity.DETAIL,
            )
            dotenv_env = dotenv.dotenv_values(project.root / path, encoding="utf-8")
            if override:
                process_env = {**process_env, **dotenv_env}
            else:
                process_env = {**dotenv_env, **process_env}
        project_env = project.environment
        this_path = project_env.get_paths()["scripts"]
        process_env.update(project_env.process_env)
        if env:
            process_env.update(env)
        if shell:
            assert isinstance(args, str)
            expanded_args: str | Sequence[str] = os.path.expandvars(args)
        else:
            assert isinstance(args, Sequence)
            command, *args = args
            if command.endswith(".py"):
                args = [command, *args]
                command = str(project.environment.interpreter.executable)
            expanded_command = self.expand_command(command)
            real_command = os.path.realpath(expanded_command)
            expanded_args = [os.path.expandvars(arg) for arg in [expanded_command, *args]]
            if (
                project_env.is_local
                and not site_packages
                and (
                    os.path.basename(real_command).startswith("python")
                    or is_path_relative_to(expanded_command, this_path)
                )
            ):
                # The executable belongs to the local packages directory.
                # Don't load system site-packages
                process_env["NO_SITE_PACKAGES"] = "1"

        cwd = project.root if chdir else None

        def forward_signal(signum: int, frame: FrameType | None) -> None:
            if sys.platform == "win32" and signum == signal.SIGINT:
                signum = signal.SIGTERM
            process.send_signal(signum)

        handle_term = signal.signal(signal.SIGTERM, forward_signal)
        handle_int = signal.signal(signal.SIGINT, forward_signal)
        process = subprocess.Popen(expanded_args, cwd=cwd, env=process_env, shell=shell, bufsize=0)
        process.wait()
        signal.signal(signal.SIGTERM, handle_term)
        signal.signal(signal.SIGINT, handle_int)
        return process.returncode

    def run_task(self, task: Task, args: Sequence[str] = (), opts: TaskOptions | None = None) -> int:
        kind, _, value, options = task
        shell = False
        if kind == "cmd":
            if isinstance(value, str):
                cmd, interpolated = interpolate(value, args)
                value = shlex.split(cmd)
            else:
                agg = [interpolate(part, args) for part in value]
                interpolated = any(row[1] for row in agg)
                # In case of multiple default, we need to split the resulting string.
                parts: Iterator[list[str]] = (
                    shlex.split(part) if interpolated else [part] for part, interpolated in agg
                )
                # We flatten the nested list to obtain a list of arguments
                value = list(itertools.chain(*parts))
            args = value if interpolated else [*value, *args]
        elif kind == "shell":
            assert isinstance(value, str)
            script, interpolated = interpolate(value, args)
            args = script if interpolated else " ".join([script, *args])
            shell = True
        elif kind == "call":
            assert isinstance(value, str)
            module, _, func = value.partition(":")
            if not module or not func:
                raise PdmUsageError("Python callable must be in the form <module_name>:<callable_name>")
            short_name = "_1"
            if re.search(r"\(.*?\)", func) is None:
                func += "()"
            args = ["python", "-c", f"import sys, {module} as {short_name};sys.exit({short_name}.{func})", *list(args)]
        elif kind == "composite":
            assert isinstance(value, list)

        self.project.core.ui.echo(
            f"Running {task}: [success]{args}[/]",
            err=True,
            verbosity=termui.Verbosity.DETAIL,
        )
        if kind == "composite":
            args = list(args)
            should_interpolate = any(RE_ARGS_PLACEHOLDER.search(script) for script in value)
            should_interpolate = should_interpolate or any(RE_PDM_PLACEHOLDER.search(script) for script in value)
            code = 0
            for script in value:
                if should_interpolate:
                    script, _ = interpolate(script, args)
                split = shlex.split(script)
                cmd = split[0]
                subargs = split[1:] + ([] if should_interpolate else args)
                code = self.run(cmd, subargs, options, chdir=True)
                if code != 0:
                    return code
            return code
        return self._run_process(
            args,
            chdir=True,
            shell=shell,
            **exec_opts(self.global_options, options, opts),
        )

    def run(self, command: str, args: list[str], opts: TaskOptions | None = None, chdir: bool = False) -> int:
        if command in self.hooks.skip:
            return 0
        task = self.get_task(command)
        if task is not None:
            self.hooks.try_emit("pre_script", script=command, args=args)
            pre_task = self.get_task(f"pre_{command}")
            if pre_task is not None and self.hooks.should_run(pre_task.name):
                code = self.run_task(pre_task, opts=opts)
                if code != 0:
                    return code
            code = self.run_task(task, args, opts=opts)
            if code != 0:
                return code
            post_task = self.get_task(f"post_{command}")
            if post_task is not None and self.hooks.should_run(post_task.name):
                code = self.run_task(post_task, opts=opts)
            self.hooks.try_emit("post_script", script=command, args=args)
            return code
        else:
            return self._run_process(
                [command, *args],
                chdir=chdir,
                **exec_opts(self.global_options, opts),
            )

    def show_list(self) -> None:
        if not self.project.scripts:
            return
        columns = ["Name", "Type", "Description"]
        result = []
        for name in sorted(self.project.scripts):
            if name.startswith("_"):
                continue
            task = self.get_task(name)
            assert task is not None
            result.append(
                (
                    f"[success]{name}[/]",
                    task.kind,
                    task.short_description,
                )
            )
        self.project.core.ui.display_columns(result, columns)

    def as_json(self) -> dict[str, Any]:
        out = {}
        for name in sorted(self.project.scripts):
            if name == "_":
                data = out["_"] = dict(name="_", kind="shared", help="Shared options", **self.global_options)
                _fix_env_file(data)
                continue
            task = self.get_task(name)
            assert task is not None
            data = out[name] = {
                "name": name,
                "kind": task.kind,
                "help": task.short_description,
                "args": task.args,  # type: ignore[dict-item]
            }
            data.update(**task.options)
            _fix_env_file(data)
        return out


def _fix_env_file(data: dict[str, Any]) -> dict[str, Any]:
    env_file = data.get("env_file")
    if isinstance(env_file, dict):
        del data["env_file"]
        data["env_file.override"] = env_file.get("override")
    return data


class Command(BaseCommand):
    """Run commands or scripts with local packages loaded"""

    runner_cls: type[TaskRunner] = TaskRunner
    arguments = (*BaseCommand.arguments, skip_option, venv_option)

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        action = parser.add_mutually_exclusive_group()
        action.add_argument(
            "-l",
            "--list",
            action="store_true",
            help="Show all available scripts defined in pyproject.toml",
        )
        action.add_argument(
            "-j",
            "--json",
            action="store_true",
            help="Output all scripts infos in JSON",
        )
        exec = parser.add_argument_group("Execution parameters")
        exec.add_argument(
            "-s",
            "--site-packages",
            action="store_true",
            help="Load site-packages from the selected interpreter",
        )
        exec.add_argument("script", nargs="?", help="The command to run")
        exec.add_argument(
            "args",
            nargs=argparse.REMAINDER,
            help="Arguments that will be passed to the command",
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        check_project_file(project)
        hooks = HookManager(project, options.skip)
        runner = self.runner_cls(project, hooks=hooks)
        if options.list:
            return runner.show_list()
        if options.json:
            return print_json(data=runner.as_json())
        if options.site_packages:
            runner.global_options.update({"site_packages": options.site_packages})
        if not options.script:
            project.core.ui.warn("No command is given, default to the Python REPL.")
            options.script = "python"
        hooks.try_emit("pre_run", script=options.script, args=options.args)
        exit_code = runner.run(options.script, options.args)
        hooks.try_emit("post_run", script=options.script, args=options.args)
        sys.exit(exit_code)


def run_script_if_present(script_name: str) -> Callable:
    """Helper to create a signal handler to run specific script"""

    def handler(sender: Project, hooks: HookManager, **kwargs: Any) -> None:
        runner = TaskRunner(sender, hooks)
        task = runner.get_task(script_name)
        if task is None:
            return
        exit_code = runner.run_task(task)
        if exit_code != 0:
            sys.exit(exit_code)

    return handler


for hook in pdm_signals:
    pdm_signals.signal(hook).connect(run_script_if_present(hook), weak=False)
