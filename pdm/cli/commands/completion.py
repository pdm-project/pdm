import argparse
import importlib.resources
import sys
from typing import List

from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import Option
from pdm.exceptions import PdmUsageError
from pdm.project import Project


class Command(BaseCommand):
    """Generate completion scripts for the given shell"""

    arguments: List[Option] = []
    SUPPORTED_SHELLS = ("bash", "zsh", "fish", "powershell")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "shell",
            nargs="?",
            help="The shell to generate the scripts for. "
            "If not given, PDM will properly guess from `SHELL` env var.",
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        import shellingham

        shell = options.shell or shellingham.detect_shell()[0]
        if shell not in self.SUPPORTED_SHELLS:
            raise PdmUsageError(f"Unsupported shell: {shell}")
        suffix = "ps1" if shell == "powershell" else shell
        completion = importlib.resources.read_text(
            "pdm.cli.completions", f"pdm.{suffix}"
        )
        project.core.ui.echo(completion.replace("%{python_executable}", sys.executable))
