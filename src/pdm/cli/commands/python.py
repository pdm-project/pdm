from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import verbose_option
from pdm.exceptions import InstallationError
from pdm.models.python import PythonInfo

if TYPE_CHECKING:
    from argparse import ArgumentParser, Namespace, _SubParsersAction
    from typing import Any

    from pdm.project.core import Project


class Command(BaseCommand):
    """Manage installed Python interpreters"""

    arguments = ()

    def add_arguments(self, parser: ArgumentParser) -> None:
        self.parser = parser
        subparsers = parser.add_subparsers(title="commands", metavar="")
        ListCommand.register_to(subparsers, name="list")
        RemoveCommand.register_to(subparsers, name="remove")
        InstallCommand.register_to(subparsers, name="install")

    @classmethod
    def register_to(cls, subparsers: _SubParsersAction, name: str | None = None, **kwargs: Any) -> None:
        return super().register_to(subparsers, name, aliases=["py"], **kwargs)

    def handle(self, project: Project, options: Namespace) -> None:
        self.parser.print_help()


class ListCommand(BaseCommand):
    """List all Python interpreters installed with PDM"""

    arguments = (verbose_option,)

    def handle(self, project: Project, options: Namespace) -> None:
        from findpython.providers.rye import RyeProvider

        ui = project.core.ui
        provider = RyeProvider(root=Path(project.config["python.install_root"]).expanduser())
        for version in provider.find_pythons():
            ui.echo(f"[success]{version.implementation.lower()}@{version.version}[/] ({version.executable})")


class RemoveCommand(BaseCommand):
    """Remove a Python interpreter installed with PDM"""

    arguments = (verbose_option,)

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("version", help="The Python version to remove. E.g. cpython@3.10.3")

    def handle(self, project: Project, options: Namespace) -> None:
        ui = project.core.ui
        root = Path(project.config["python.install_root"]).expanduser()
        if not root.exists():
            ui.error(f"No Python interpreter found for {options.version!r}")
            sys.exit(1)
        version = options.version.lower()
        if "@" not in version:  # pragma: no cover
            version = f"cpython@{version}"
        matched = next((child for child in root.iterdir() if child.name == version), None)
        if not matched:
            ui.error(f"No Python interpreter found for {options.version!r}")
            ui.echo("Installed Pythons:", err=True)
            for child in root.iterdir():
                ui.echo(f"  {child.name}", err=True)
            sys.exit(1)
        shutil.rmtree(matched, ignore_errors=True)
        ui.echo(f"[success]Removed installed[/] {options.version}")


class InstallCommand(BaseCommand):
    """Install a Python interpreter with PDM"""

    arguments = (verbose_option,)

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("version", help="The Python version to install. E.g. cpython@3.10.3", nargs="?")
        parser.add_argument("--list", "-l", action="store_true", help="List all available Python versions")

    def handle(self, project: Project, options: Namespace) -> None:
        from pbs_installer._versions import PYTHON_VERSIONS

        if options.list:
            for version in PYTHON_VERSIONS:
                project.core.ui.echo(str(version))
            return
        self.install_python(project, options.version)

    @staticmethod
    def install_python(project: Project, request: str) -> PythonInfo:
        from pbs_installer import download, get_download_link, install_file
        from pbs_installer._install import THIS_ARCH

        from pdm.termui import logger

        ui = project.core.ui
        root = Path(project.config["python.install_root"]).expanduser()

        implementation, _, version = request.rpartition("@")
        implementation = implementation.lower() or "cpython"
        version, _, arch = version.partition("-")
        arch = "x86" if arch == "32" else (arch or THIS_ARCH)

        ver, python_file = get_download_link(version, implementation=implementation, arch=arch)
        with ui.open_spinner(f"Downloading [success]{ver}[/]") as spinner:
            destination = root / str(ver)
            logger.debug("Installing %s to %s", ver, destination)
            if not destination.exists():
                destination.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile() as tf:
                    tf.close()
                    original_filename = download(python_file, tf.name)
                    spinner.update(f"Installing [success]{ver}[/]")
                    install_file(tf.name, destination, original_filename, build_dir=False)

        interpreter = destination / "bin" / "python3" if sys.platform != "win32" else destination / "python.exe"
        if not interpreter.exists():
            raise InstallationError("Installation failed")

        python_info = PythonInfo.from_path(interpreter)
        ui.echo(f"[success]Successfully installed[/] {python_info.implementation}@{python_info.version}")
        ui.echo(f"[info]Version:[/] {python_info.version}")
        ui.echo(f"[info]Executable:[/] {python_info.path}")
        return python_info
