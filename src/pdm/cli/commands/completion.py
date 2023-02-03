from __future__ import annotations

import argparse
import sys

from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import Option
from pdm.compat import resources_read_text
from pdm.exceptions import PdmUsageError
from pdm.project import Project


class Command(BaseCommand):
    """Generate completion scripts for the given shell"""

    arguments: list[Option] = []
    SUPPORTED_SHELLS = ("bash", "zsh", "fish", "powershell", "pwsh")

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
        suffix = "ps1" if shell in {"powershell", "pwsh"} else shell
        completion = resources_read_text("pdm.cli.completions", f"pdm.{suffix}")
        # Can't use rich print or otherwise the rich markups will be interpreted
        print(completion.replace("%{python_executable}", sys.executable))
