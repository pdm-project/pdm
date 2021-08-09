from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys

import click

from pdm import termui
from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import verbose_option
from pdm.cli.utils import Package, build_dependency_graph
from pdm.models.environment import WorkingSet
from pdm.project import Project
from pdm.utils import normalize_name

if sys.version_info >= (3, 8):
    import importlib.metadata as importlib_metadata
else:
    import importlib_metadata

from pip import __file__ as pip_location


def _all_plugins() -> list[str]:
    result: set[str] = set()
    for dist in importlib_metadata.distributions():
        if any(ep.group in ("pdm", "pdm.plugin") for ep in dist.entry_points):
            result.add(normalize_name(dist.metadata["Name"]))
    return sorted(result)


def run_pip(args: list[str]) -> bytes:
    return subprocess.check_output(
        [sys.executable, "-I", os.path.dirname(pip_location)] + args,
        stderr=subprocess.STDOUT,
    )


class Command(BaseCommand):
    """Manage the PDM plugins"""

    arguments = [verbose_option]

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        subparsers = parser.add_subparsers(title="Sub commands")
        ListCommand.register_to(subparsers)
        AddCommand.register_to(subparsers)
        RemoveCommand.register_to(subparsers)
        parser.set_defaults(search_parent=False)
        self.parser = parser

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        self.parser.print_help()


class ListCommand(BaseCommand):
    """List all plugins installed with PDM"""

    arguments = [verbose_option]
    name = "list"

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        plugins = _all_plugins()
        echo = project.core.ui.echo
        if not plugins:
            echo("No plugin is installed with PDM", err=True)
            sys.exit(1)
        echo("Installed plugins:", err=True)
        for plugin in plugins:
            metadata = importlib_metadata.metadata(plugin)
            echo(
                f"{termui.green(metadata['Name'])} {termui.yellow(metadata['Version'])}"
            )
            if metadata["Summary"]:
                echo(f"    {metadata['Summary']}")


class AddCommand(BaseCommand):
    """Install new plugins with PDM"""

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
            help="Specify one or many plugin names, "
            "each package can have a version specifier",
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        pip_args = ["install"] + shlex.split(options.pip_args) + options.packages

        project.core.ui.echo(
            f"Running pip command: {pip_args}", verbosity=termui.DETAIL
        )
        with project.core.ui.open_spinner(
            f"Installing plugins: {options.packages}"
        ) as spinner:
            try:
                run_pip(pip_args)
            except subprocess.CalledProcessError as e:
                spinner.fail("Installation failed: \n" + e.output.decode("utf8"))
                sys.exit(1)
            else:
                spinner.succeed("Installation succeeds.")


class RemoveCommand(BaseCommand):
    """Remove plugins from PDM's environment"""

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
            "packages", nargs="+", help="Specify one or many plugin names"
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
        plugins = _all_plugins()
        valid_packages = [p for p in options.packages if normalize_name(p) in plugins]
        packages_to_remove = self._resolve_dependencies_to_remove(valid_packages)
        if not packages_to_remove:
            project.core.ui.echo("No package to remove.", err=True)
            sys.exit(1)
        if not (
            options.yes
            or click.confirm(f"Will remove: {packages_to_remove}, continue?")
        ):
            return
        pip_args = (
            ["uninstall", "-y"] + shlex.split(options.pip_args) + packages_to_remove
        )

        project.core.ui.echo(
            f"Running pip command: {pip_args}", verbosity=termui.DETAIL
        )
        with project.core.ui.open_spinner(
            f"Uninstalling plugins: {valid_packages}"
        ) as spinner:
            try:
                run_pip(pip_args)
            except subprocess.CalledProcessError as e:
                spinner.fail("Uninstallation failed: \n" + e.output.decode("utf8"))
                sys.exit(1)
            else:
                spinner.succeed("Uninstallation succeeds.")
