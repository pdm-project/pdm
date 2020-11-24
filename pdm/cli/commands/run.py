import argparse
import hashlib
import os
import re
import shlex
import subprocess
import sys
from typing import List, Union

from pdm.cli.commands.base import BaseCommand
from pdm.exceptions import PdmUsageError
from pdm.iostream import stream
from pdm.project import Project
from pdm.utils import find_project_root


class Command(BaseCommand):
    """Run commands or scripts with local packages loaded"""

    OPTIONS = ["env", "help"]
    TYPES = ["cmd", "shell", "call"]

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-l",
            "--list",
            action="store_true",
            help="Show all available scripts defined in pyproject.toml",
        )
        parser.add_argument("command", nargs="?", help="The command to run")
        parser.add_argument(
            "args",
            nargs=argparse.REMAINDER,
            help="Arguments that will be passed to the command",
        )

    @staticmethod
    def _run_command(
        project: Project,
        args: Union[List[str], str],
        shell=False,
        env=None,
    ) -> None:
        with project.environment.activate():
            if env:
                os.environ.update(env)
            if shell:
                sys.exit(subprocess.call(os.path.expandvars(args), shell=True))

            command, *args = args
            expanded_command = project.environment.which(command)
            if not expanded_command:
                raise PdmUsageError(
                    "Command {} is not found on your PATH.".format(
                        stream.green(f"'{command}'")
                    )
                )
            expanded_command = os.path.expanduser(os.path.expandvars(expanded_command))
            expanded_args = [
                os.path.expandvars(arg) for arg in [expanded_command] + args
            ]
            if os.name == "nt" or "CI" in os.environ:
                # In order to make sure pytest is playing well,
                # don't hand over the process under a testing environment.
                sys.exit(subprocess.call(expanded_args))
            else:
                os.execv(expanded_command, expanded_args)

    def _normalize_script(self, script):
        if not getattr(script, "items", None):
            # Must be a string, regard as the same as {cmd = "..."}
            kind = "cmd"
            value = str(script)
            options = {}
        else:
            script = dict(script)  # to remove the effect of tomlkit's container type.
            for key in self.TYPES:
                if key in script:
                    kind = key
                    value = script.pop(key)
                    break
            else:
                raise PdmUsageError(
                    f"Script type must be one of ({', '.join(self.TYPES)})"
                )
            options = script.copy()
        if not all(key in self.OPTIONS for key in options):
            raise PdmUsageError(
                f"pdm scripts only accept options: ({', '.join(self.OPTIONS)})"
            )
        return kind, value, options

    def _run_script(self, project: Project, script_name: str, args: List[str]) -> None:
        script = project.scripts[script_name]
        kind, value, options = self._normalize_script(script)
        if kind == "cmd":
            args = shlex.split(value) + list(args)
        elif kind == "shell":
            args = " ".join([value] + list(args))
            options["shell"] = True
        elif kind == "call":
            module, _, func = value.partition(":")
            if not module or not func:
                raise PdmUsageError(
                    "Python callable must be in the form <module_name>:<callable_name>"
                )
            short_name = "_" + hashlib.sha1(module.encode()).hexdigest()[:6]
            if re.search(r"\(.*?\)", func) is None:
                func += "()"
            args = [
                "python",
                "-c",
                f"import sys, {module} as {short_name};"
                f"sys.exit({short_name}.{func})",
            ] + args
        stream.echo(f"Running {kind} script: {stream.green(str(args))}", err=True)
        return self._run_command(project, args, **options)

    def _show_list(self, project: Project) -> None:
        if not project.scripts:
            return
        columns = ["Name", "Type", "Script", "Description"]
        result = []
        for name, script in project.scripts.items():
            kind, value, options = self._normalize_script(script)
            result.append((stream.green(name), kind, value, options.get("help", "")))
        stream.display_columns(result, columns)

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        if options.list:
            return self._show_list(project)
        if project.scripts and options.command in project.scripts:
            self._run_script(project, options.command, options.args)
        elif os.path.isfile(options.command) and options.command.endswith(".py"):
            # Allow executing py scripts like `pdm run my_script.py`.
            # In this case, the nearest `__pypackages__` will be loaded as
            # the library source.
            new_root = find_project_root(os.path.abspath(options.command))
            project = Project(new_root) if new_root else project
            self._run_command(project, ["python", options.command] + options.args)
        else:
            self._run_command(project, [options.command] + options.args)
