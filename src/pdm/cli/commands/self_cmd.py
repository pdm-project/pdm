from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from typing import Iterable

from packaging.version import parse

from pdm import termui
from pdm.cli.actions import get_latest_pdm_version_from_pypi
from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import verbose_option
from pdm.cli.utils import Package, build_dependency_graph
from pdm.compat import Distribution, importlib_metadata
from pdm.models.environment import BareEnvironment, WorkingSet
from pdm.project import Project
from pdm.utils import normalize_name

PDM_REPO = "https://github.com/pdm-project/pdm"


def _get_distributions() -> Iterable[Distribution]:
    return importlib_metadata.distributions()


def list_distributions(plugin_only: bool = False) -> list[Distribution]:
    result: list[Distribution] = []
    for dist in _get_distributions():
        if not plugin_only or any(
            ep.group in ("pdm", "pdm.plugin") for ep in dist.entry_points
        ):
            result.append(dist)
    return sorted(result, key=lambda d: d.metadata["Name"] or "UNKNOWN")


def run_pip(project: Project, args: list[str]) -> bytes:
    env = BareEnvironment(project)
    project.environment = env
    return subprocess.check_output(env.pip_command + args, stderr=subprocess.STDOUT)


class Command(BaseCommand):
    """Manage the PDM program itself (previously known as plugin)"""

    arguments = [verbose_option]
    name = "self"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        subparsers = parser.add_subparsers(title="Sub commands")
        ListCommand.register_to(subparsers)
        AddCommand.register_to(subparsers)
        RemoveCommand.register_to(subparsers)
        UpdateCommand.register_to(subparsers)
        parser.set_defaults(search_parent=False)
        self.parser = parser

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        self.parser.print_help()


class ListCommand(BaseCommand):
    """List all packages installed with PDM"""

    arguments = [verbose_option]
    name = "list"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--plugins", action="store_true", help="List plugins only")

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        distributions = list_distributions(plugin_only=options.plugins)
        echo = project.core.ui.echo
        if not distributions:
            # This should not happen when plugin_only is False
            echo("No plugin is installed with PDM", err=True)
            sys.exit(1)
        echo("Installed packages:", err=True)
        rows = []
        for dist in distributions:
            metadata = dist.metadata
            rows.append(
                (
                    f"[green]{metadata['Name']}[/]",
                    f"[yellow]{metadata['Version']}[/]",
                    metadata["Summary"] or "",
                ),
            )
        project.core.ui.display_columns(rows)


class AddCommand(BaseCommand):
    """Install packages to the PDM's environment"""

    arguments = [verbose_option]
    name = "add"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--pip-args",
            help="Arguments that will be passed to pip install",
            default="",
        )
        parser.add_argument(
            "packages",
            nargs="+",
            help="Specify one or many package names, "
            "each package can have a version specifier",
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        pip_args = ["install"] + shlex.split(options.pip_args) + options.packages

        project.core.ui.echo(
            f"Running pip command: {pip_args}", verbosity=termui.Verbosity.DETAIL
        )
        try:
            with project.core.ui.open_spinner(
                f"Installing packages: {options.packages}"
            ):
                run_pip(project, pip_args)
        except subprocess.CalledProcessError as e:
            project.core.ui.echo(
                "[red]Installation failed:[/]\n" + e.output.decode("utf8"), err=True
            )
            sys.exit(1)
        else:
            project.core.ui.echo("[green]Installation succeeds.[/]")


class RemoveCommand(BaseCommand):
    """Remove packages from PDM's environment"""

    arguments = [verbose_option]
    name = "remove"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--pip-args",
            help="Arguments that will be passed to pip uninstall",
            default="",
        )
        parser.add_argument(
            "-y", "--yes", action="store_true", help="Answer yes on the question"
        )
        parser.add_argument(
            "packages", nargs="+", help="Specify one or many package names"
        )

    def _resolve_dependencies_to_remove(self, packages: list[str]) -> list[str]:
        """Perform a BFS to find all unneeded dependencies"""
        result: set[str] = set()
        to_resolve = list(packages)

        ws = WorkingSet()
        graph = build_dependency_graph(ws)
        while to_resolve:
            temp: list[Package] = []
            for name in to_resolve:
                key = normalize_name(name)
                if key in ws:
                    result.add(key)
                package = Package(key, "0.0.0", {})
                if package not in graph:
                    continue
                for dep in graph.iter_children(package):
                    temp.append(dep)
                graph.remove(package)

            to_resolve.clear()
            for dep in temp:
                if not any(graph.iter_parents(dep)) and dep.name != "pdm":
                    to_resolve.append(dep.name)

        return sorted(result)

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        packages_to_remove = self._resolve_dependencies_to_remove(options.packages)
        if not packages_to_remove:
            project.core.ui.echo("No package to remove.", err=True)
            sys.exit(1)
        if not (
            options.yes
            or termui.confirm(
                f"Will remove: {packages_to_remove}, continue?", default=True
            )
        ):
            return
        pip_args = (
            ["uninstall", "-y"] + shlex.split(options.pip_args) + packages_to_remove
        )

        project.core.ui.echo(
            f"Running pip command: {pip_args}", verbosity=termui.Verbosity.DETAIL
        )
        try:
            with project.core.ui.open_spinner(
                f"Uninstalling packages: [green]{', '.join(options.packages)}[/]"
            ):
                run_pip(project, pip_args)
        except subprocess.CalledProcessError as e:
            project.core.ui.echo(
                "[red]Uninstallation failed:[/]\n" + e.output.decode("utf8"), err=True
            )
            sys.exit(1)
        else:
            project.core.ui.echo("[green]Uninstallation succeeds.[/]")


class UpdateCommand(BaseCommand):
    """Update PDM itself"""

    arguments = [verbose_option]
    name = "update"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--head",
            action="store_true",
            help="Update to the latest commit on the main branch",
        )
        parser.add_argument(
            "--pre",
            help="Update to the latest prerelease version",
            action="store_true",
        )
        parser.add_argument(
            "--pip-args",
            help="Additional arguments that will be passed to pip install",
            default="",
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        from pdm.__version__ import parsed_version

        if options.head:
            package = f"pdm @ git+{PDM_REPO}@main"
            version: str | None = "HEAD"
        else:
            version = get_latest_pdm_version_from_pypi(project, options.pre)
            assert version is not None, "No version found"
            if parsed_version and parsed_version >= parse(version):
                project.core.ui.echo(f"Already up-to-date: [cyan]{parsed_version}[/]")
                return
            package = f"pdm=={version}"
        pip_args = ["install", "--upgrade"] + shlex.split(options.pip_args) + [package]
        project.core.ui.echo(
            f"Running pip command: {pip_args}", verbosity=termui.Verbosity.DETAIL
        )
        try:
            with project.core.ui.open_spinner(
                f"Updating pdm to version [cyan]{version}[/]"
            ):
                run_pip(project, pip_args)
        except subprocess.CalledProcessError as e:
            project.core.ui.echo(
                f"[red]Installing version [cyan]{version}[/] failed:[/]\n"
                + e.output.decode("utf8"),
                err=True,
            )
            sys.exit(1)
        else:
            project.core.ui.echo(
                f"[green]Installing version [cyan]{version}[/] succeeds.[/]"
            )
