from __future__ import annotations

import argparse
import importlib
import itertools
import os
import pkgutil
import sys
from pathlib import Path
from typing import Any, List, Optional, Type, cast

import click
from resolvelib import Resolver

from pdm import termui
from pdm.cli.actions import check_update, migrate_pyproject, print_pep582_command
from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import ignore_python_option, pep582_option, verbose_option
from pdm.cli.utils import PdmFormatter
from pdm.exceptions import PdmUsageError
from pdm.installers import InstallManager, Synchronizer
from pdm.models.repositories import PyPIRepository
from pdm.project import Project
from pdm.project.config import Config, ConfigItem

if sys.version_info >= (3, 8):
    import importlib.metadata as importlib_metadata
else:
    import importlib_metadata

COMMANDS_MODULE_PATH: str = importlib.import_module(
    "pdm.cli.commands"
).__path__  # type: ignore


class Core:
    """A high level object that manages all classes and configurations"""

    project_class = Project
    repository_class = PyPIRepository
    resolver_class = Resolver
    synchronizer_class = Synchronizer
    install_manager_class = InstallManager

    def __init__(self) -> None:
        try:
            self.version = importlib_metadata.version(__name__.split(".")[0])
        except importlib_metadata.PackageNotFoundError:
            self.version = "UNKNOWN"

        self.ui = termui.UI()
        self.parser: Optional[argparse.ArgumentParser] = None
        self.subparsers: Optional[argparse._SubParsersAction] = None

    def init_parser(self) -> None:
        self.parser = argparse.ArgumentParser(
            prog="pdm",
            description="PDM - Python Development Master",
            formatter_class=PdmFormatter,
        )
        self.parser.is_root = True  # type: ignore
        self.parser.add_argument(
            "-V",
            "--version",
            action="version",
            version="{}, version {}".format(
                click.style("Python Development Master (PDM)", bold=True), self.version
            ),
            help="show the version and exit",
        )
        self.parser._positionals.title = "Commands"
        verbose_option.add_to_parser(self.parser)
        ignore_python_option.add_to_parser(self.parser)
        pep582_option.add_to_parser(self.parser)

        self.subparsers = self.parser.add_subparsers()
        for _, name, _ in pkgutil.iter_modules(COMMANDS_MODULE_PATH):
            module = importlib.import_module(f"pdm.cli.commands.{name}", __name__)
            try:
                klass = module.Command  # type: ignore
            except AttributeError:
                continue
            self.register_command(klass, klass.name or name)

    def __call__(self, *args: Any, **kwargs: Any) -> None:
        return self.main(*args, **kwargs)

    def ensure_project(
        self, options: argparse.Namespace, obj: Optional[Project]
    ) -> None:
        if obj is not None:
            options.project = obj
        if getattr(options, "project", None) is None:
            global_project = getattr(options, "global_project", None)

            default_root = (
                None
                if global_project or getattr(options, "search_parent", True)
                else "."
            )
            project = self.create_project(
                getattr(options, "project_path", None) or default_root,  # type: ignore
                is_global=global_project,
            )
            options.project = project

        migrate_pyproject(options.project)

    def create_project(
        self, root_path: str | Path | None = None, is_global: bool = False
    ) -> Project:
        """Create a new project object

        Args:
            root_path (PathLike): The path to the project root directory
            is_global (bool): Whether the project is a global project

        Returns:
            The project object
        """
        return self.project_class(self, root_path, is_global)

    def main(
        self,
        args: List[str] = None,
        prog_name: str = None,
        obj: Optional[Project] = None,
        **extra: Any,
    ) -> None:
        """The main entry function"""
        from pdm.models.pip_shims import global_tempdir_manager

        self.init_parser()
        self.load_plugins()
        assert self.parser
        assert self.subparsers
        options = self.parser.parse_args(args or None)
        self.ui.set_verbosity(options.verbose)
        if options.ignore_python:
            os.environ["PDM_IGNORE_SAVED_PYTHON"] = "1"

        if options.pep582:
            print_pep582_command(self.ui, options.pep582)
            sys.exit(0)

        self.ensure_project(options, obj)

        try:
            f = options.handler
        except AttributeError:
            self.parser.print_help()
            sys.exit(1)
        else:
            try:
                with global_tempdir_manager():
                    f(options.project, options)
            except Exception:
                etype, err, traceback = sys.exc_info()
                should_show_tb = not isinstance(err, PdmUsageError)
                if self.ui.verbosity > termui.NORMAL and should_show_tb:
                    raise cast(Exception, err).with_traceback(traceback)
                self.ui.echo(
                    f"{termui.red('[' + etype.__name__ + ']')}: {err}",  # type: ignore
                    err=True,
                )
                if should_show_tb:
                    self.ui.echo(
                        "Add '-v' to see the detailed traceback", fg="yellow", err=True
                    )
                sys.exit(1)
            else:
                if options.project.config["check_update"]:
                    check_update(options.project)

    def register_command(
        self, command: Type[BaseCommand], name: Optional[str] = None
    ) -> None:
        """Register a subcommand to the subparsers,
        with an optional name of the subcommand.

        Args:
            command (Type[pdm.cli.commands.base.BaseCommand]):
                The command class to register
            name (str): The name of the subcommand, if not given, `command.name`
                is used
        """
        assert self.subparsers
        command.register_to(self.subparsers, name)

    @staticmethod
    def add_config(name: str, config_item: ConfigItem) -> None:
        """Add a config item to the configuration class.

        Args:
            name (str): The name of the config item
            config_item (pdm.project.config.ConfigItem): The config item to add
        """
        Config.add_config(name, config_item)

    def load_plugins(self) -> None:
        """Import and load plugins under `pdm.plugin` namespace
        A plugin is a callable that accepts the core object as the only argument.

        Example:
            ```python
            def my_plugin(core: pdm.core.Core) -> None:
                ...
            ```
        """
        entry_points = importlib_metadata.entry_points()
        for plugin in itertools.chain(
            entry_points.get("pdm", []), entry_points.get("pdm.plugin", [])
        ):
            plugin.load()(self)


def main(args: Optional[List[str]] = None) -> None:
    """The CLI entry function"""
    return Core().main(args)
