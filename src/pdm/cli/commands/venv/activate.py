import argparse
import shlex
from pathlib import Path

import shellingham

from pdm.cli.commands.base import BaseCommand
from pdm.cli.commands.venv.utils import get_venv_with_name
from pdm.cli.options import verbose_option
from pdm.models.venv import VirtualEnv
from pdm.project import Project


class ActivateCommand(BaseCommand):
    """Activate the virtualenv with the given name"""

    arguments = [verbose_option]

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("env", nargs="?", help="The key of the virtualenv")

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        if options.env:
            venv = get_venv_with_name(project, options.env)
        else:
            # Use what is saved in .pdm-python
            interpreter = project._saved_python
            if not interpreter:
                project.core.ui.echo(
                    "The project doesn't have a saved python.path. Run [success]pdm use[/] to pick one.",
                    style="warning",
                    err=True,
                )
                raise SystemExit(1)
            venv_like = VirtualEnv.from_interpreter(Path(interpreter))
            if venv_like is None:
                project.core.ui.echo(
                    f"Can't activate a non-venv Python [success]{interpreter}[/], "
                    "you can specify one with [success]pdm venv activate <env_name>[/]",
                    style="warning",
                    err=True,
                )
                raise SystemExit(1)
            venv = venv_like
        project.core.ui.echo(self.get_activate_command(venv))

    def get_activate_command(self, venv: VirtualEnv) -> str:  # pragma: no cover
        shell, _ = shellingham.detect_shell()
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
            return f"{command} {shlex.quote(str(activate_script))}"
        # Conda backed virtualenvs don't have activate scripts
        return f"conda activate {shlex.quote(str(venv.root))}"
