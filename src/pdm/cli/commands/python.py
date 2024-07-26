from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import verbose_option
from pdm.environments import BareEnvironment
from pdm.exceptions import InstallationError, PdmArgumentError
from pdm.models.python import PythonInfo
from pdm.termui import Verbosity
from pdm.utils import get_all_installable_python_versions

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
        ui.echo(f"[success]Removed installed[/] {options.version}", verbosity=Verbosity.NORMAL)


class InstallCommand(BaseCommand):
    """Install a Python interpreter with PDM"""

    arguments = (verbose_option,)

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "version",
            help="The Python version to install (e.g. cpython@3.10.3). If left empty, "
            "highest cPython version that matches this platform/arch is installed. "
            "If pyproject.toml with requires-python is available, this is considered as well.",
            nargs="?",
        )
        parser.add_argument("--list", "-l", action="store_true", help="List all available Python versions")
        parser.add_argument(
            "--min",
            action="store_true",
            help="Use minimum instead of highest version " "for installation if `version` is left empty",
        )

    def handle(self, project: Project, options: Namespace) -> None:
        if options.list:
            for version in get_all_installable_python_versions(build_dir=False):
                project.core.ui.echo(str(version))
            return
        version = options.version
        if version is None:
            match = project.get_best_matching_cpython_version(options.min)
            if match is not None:
                version = str(match)

        if version is None:
            raise PdmArgumentError("Please specify a Python version to be installed. E.g. cpython@3.10.3")

        self.install_python(project, version)

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

        ver, python_file = get_download_link(version, implementation=implementation, arch=arch, build_dir=False)
        with ui.open_spinner(f"Downloading [success]{ver}[/]") as spinner:
            destination = root / str(ver)
            interpreter = destination / "bin" / "python3" if sys.platform != "win32" else destination / "python.exe"
            logger.debug("Installing %s to %s", ver, destination)
            env = BareEnvironment(project)
            if not destination.exists() or not interpreter.exists():
                shutil.rmtree(destination, ignore_errors=True)
                destination.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile() as tf:
                    tf.close()
                    original_filename = download(python_file, tf.name, env.session)
                    spinner.update(f"Installing [success]{ver}[/]")
                    install_file(tf.name, destination, original_filename)

        if not interpreter.exists():
            raise InstallationError("Installation failed, please try again.")

        python_info = PythonInfo.from_path(interpreter)
        ui.echo(
            f"[success]Successfully installed[/] {python_info.implementation}@{python_info.version}",
            verbosity=Verbosity.NORMAL,
        )
        ui.echo(f"[info]Version:[/] {python_info.version}", verbosity=Verbosity.NORMAL)
        ui.echo(f"[info]Executable:[/] {python_info.path}", verbosity=Verbosity.NORMAL)
        return python_info
