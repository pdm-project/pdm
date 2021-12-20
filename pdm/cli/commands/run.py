import argparse
import hashlib
import os
import re
import shlex
import subprocess
import sys
from typing import Any, Mapping, MutableMapping, Optional, Sequence, Tuple, Union, cast

from pdm import termui
from pdm.cli.actions import PEP582_PATH
from pdm.cli.commands.base import BaseCommand
from pdm.cli.utils import check_project_file
from pdm.exceptions import PdmUsageError
from pdm.project import Project
from pdm.utils import is_path_relative_to


class Command(BaseCommand):
    """Run commands or scripts with local packages loaded"""

    OPTIONS = ["env", "env_file", "help", "site_packages"]
    TYPES = ["cmd", "shell", "call"]

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

    @staticmethod
    def _run_command(
        project: Project,
        args: Union[Sequence[str], str],
        chdir: bool = False,
        shell: bool = False,
        site_packages: bool = False,
        env: Optional[Mapping[str, str]] = None,
        env_file: Optional[str] = None,
    ) -> None:
        if "PYTHONPATH" in os.environ:
            pythonpath = os.pathsep.join([PEP582_PATH, os.getenv("PYTHONPATH", "")])
        else:
            pythonpath = PEP582_PATH
        project_env = project.environment
        this_path = project_env.get_paths()["scripts"]
        python_root = os.path.dirname(project.python.executable)
        new_path = os.pathsep.join([this_path, os.getenv("PATH", ""), python_root])
        os.environ.update(
            {
                "PYTHONPATH": pythonpath,
                "PATH": new_path,
                "PDM_PROJECT_ROOT": str(project.root),
            }
        )
        if project_env.packages_path:
            os.environ.update({"PEP582_PACKAGES": str(project_env.packages_path)})
        if env_file:
            import dotenv

            project.core.ui.echo(
                f"Loading .env file: {termui.green(env_file)}", err=True
            )
            dotenv.load_dotenv(
                project.root.joinpath(env_file).as_posix(), override=True
            )
        if env:
            os.environ.update(env)
        if shell:
            assert isinstance(args, str)
            sys.exit(subprocess.call(os.path.expandvars(args), shell=True))

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
        expanded_args = [os.path.expandvars(arg) for arg in [expanded_command] + args]
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
            os.environ["NO_SITE_PACKAGES"] = "1"
        if os.name == "nt" or "CI" in os.environ:
            # In order to make sure pytest is playing well,
            # don't hand over the process under a testing environment.
            cwd = project.root if chdir else None
            sys.exit(subprocess.call(expanded_args, cwd=cwd))
        else:
            if chdir:
                os.chdir(project.root)
            os.execv(expanded_command, expanded_args)

    def _normalize_script(
        self, script: Any
    ) -> Tuple[str, Union[Sequence[str], str], MutableMapping[str, Any]]:
        if not getattr(script, "items", None):
            # Regard as the same as {cmd = ... }
            kind = "cmd"
            value = script
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
        if any(key not in self.OPTIONS for key in options):
            raise PdmUsageError(
                f"pdm scripts only accept options: ({', '.join(self.OPTIONS)})"
            )
        return kind, value, options

    def _run_script(
        self,
        project: Project,
        script_name: str,
        args: Sequence[str],
        global_env_options: Mapping[str, Union[str, Mapping[str, str]]],
    ) -> None:
        script = project.scripts[script_name]
        kind, value, options = self._normalize_script(script)
        options.pop("help", None)
        if kind == "cmd":
            if not isinstance(value, list):
                value = shlex.split(str(value))
            args = value + list(args)
        elif kind == "shell":
            assert isinstance(value, str)
            args = " ".join([value] + list(args))  # type: ignore
            options["shell"] = True
        elif kind == "call":
            assert isinstance(value, str)
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
            ] + list(args)
        if "env" in global_env_options:
            options["env"] = {
                **cast(Mapping[str, str], global_env_options["env"]),
                **options.get("env", {}),
            }
        options["env_file"] = options.get(
            "env_file", global_env_options.get("env_file")
        )
        project.core.ui.echo(
            f"Running {kind} script: {termui.green(str(args))}", err=True
        )
        return self._run_command(project, args, chdir=True, **options)

    def _show_list(self, project: Project) -> None:
        if not project.scripts:
            return
        columns = ["Name", "Type", "Script", "Description"]
        result = []
        for name, script in project.scripts.items():
            if name == "_":
                continue
            kind, value, options = self._normalize_script(script)
            result.append(
                (termui.green(name), kind, str(value), options.get("help", ""))
            )
        project.core.ui.display_columns(result, columns)

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        check_project_file(project)
        if options.list:
            return self._show_list(project)
        global_env_options = project.scripts.get("_", {}) if project.scripts else {}
        assert isinstance(global_env_options, dict)
        global_env_options.update(site_packages=options.site_packages)
        if not options.command:
            raise PdmUsageError("No command given")
        if project.scripts and options.command in project.scripts:
            self._run_script(project, options.command, options.args, global_env_options)
        else:
            self._run_command(
                project,
                [options.command] + options.args,
                **global_env_options,  # type: ignore
            )
