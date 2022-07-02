import argparse
import shlex
from pathlib import Path

import shellingham

from pdm.cli.commands.base import BaseCommand
from pdm.cli.commands.venv.utils import BIN_DIR, iter_venvs
from pdm.cli.options import verbose_option
from pdm.project import Project
from pdm.utils import get_venv_like_prefix


class ActivateCommand(BaseCommand):
    """Activate the virtualenv with the given name"""

    arguments = [verbose_option]

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("env", nargs="?", help="The key of the virtualenv")

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        if options.env:
            venv = next(
                (venv for key, venv in iter_venvs(project) if key == options.env), None
            )
            if not venv:
                project.core.ui.echo(
                    f"No virtualenv with key [green]{options.env}[/] is found",
                    style="yellow",
                    err=True,
                )
                raise SystemExit(1)
        else:
            # Use what is saved in .pdm.toml
            interpreter = project.python_executable
            venv = get_venv_like_prefix(interpreter)
            if venv is None:
                project.core.ui.echo(
                    f"Can't activate a non-venv Python [green]{interpreter}[/], "
                    "you can specify one with [green]pdm venv activate <env_name>[/]",
                    style="yellow",
                    err=True,
                )
                raise SystemExit(1)
        project.core.ui.echo(self.get_activate_command(venv))

    def get_activate_command(self, venv: Path) -> str:  # pragma: no cover
        shell, _ = shellingham.detect_shell()
        if shell == "fish":
            command, filename = "source", "activate.fish"
        elif shell == "csh":
            command, filename = "source", "activate.csh"
        elif shell in ["powershell", "pwsh"]:
            command, filename = ".", "Activate.ps1"
        else:
            command, filename = "source", "activate"
        activate_script = venv / BIN_DIR / filename
        if activate_script.exists():
            return f"{command} {shlex.quote(str(activate_script))}"
        # Conda backed virtualenvs don't have activate scripts
        return f"conda activate {shlex.quote(str(venv))}"
