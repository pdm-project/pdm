import argparse
import platform
import shlex
from pathlib import Path

import shellingham

from pdm.cli.commands.base import BaseCommand
from pdm.cli.commands.venv.utils import get_venv_with_name
from pdm.cli.options import verbose_option
from pdm.models.venv import VirtualEnv
from pdm.project import Project


class ActivateCommand(BaseCommand):
    """Print the command to activate the virtualenv with the given name"""

    arguments = (verbose_option,)

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("env", nargs="?", help="The key of the virtualenv")

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        if options.env:
            venv = get_venv_with_name(project, options.env)
        else:
            # Use what is saved in .pdm-python
            interpreter = project._saved_python
            if not interpreter:
                project.core.ui.warn(
                    "The project doesn't have a saved python.path. Run [success]pdm use[/] to pick one."
                )
                raise SystemExit(1)
            venv_like = VirtualEnv.from_interpreter(Path(interpreter))
            if venv_like is None:
                project.core.ui.warn(
                    f"Can't activate a non-venv Python [success]{interpreter}[/], "
                    "you can specify one with [success]pdm venv activate <env_name>[/]",
                )
                raise SystemExit(1)
            venv = venv_like
        project.core.ui.echo(self.get_activate_command(venv))

    def get_activate_command(self, venv: VirtualEnv) -> str:  # pragma: no cover
        try:
            shell, _ = shellingham.detect_shell()
        except shellingham.ShellDetectionFailure:
            shell = ""
        if shell == "fish":
            command, filename = "source", "activate.fish"
        elif shell == "csh":
            command, filename = "source", "activate.csh"
        elif shell in ["powershell", "pwsh"]:
            command, filename = ".", "Activate.ps1"
        else:
            command, filename = "source", "activate"
        activate_script = venv.interpreter.with_name(filename)
        if activate_script.exists():
            if platform.system() == "Windows":
                return f"{self.quote(str(activate_script), shell)}"
            return f"{command} {self.quote(str(activate_script), shell)}"
        # Conda backed virtualenvs don't have activate scripts
        return f"conda activate {self.quote(str(venv.root), shell)}"

    @staticmethod
    def quote(command: str, shell: str) -> str:
        if shell in ["powershell", "pwsh"]:
            return "{}".format(command.replace("'", "''"))
        return shlex.quote(command)
