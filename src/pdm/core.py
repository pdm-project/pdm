r"""
    ____  ____  __  ___
   / __ \/ __ \/  |/  /
  / /_/ / / / / /|_/ /
 / ____/ /_/ / /  / /
/_/   /_____/_/  /_/
"""
from __future__ import annotations

import argparse
import importlib
import itertools
import os
import pkgutil
import sys
from pathlib import Path
from typing import Any, Iterable, cast

from resolvelib import Resolver

from pdm import termui
from pdm.__version__ import __version__
from pdm.cli.actions import check_update, print_pep582_command
from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import ignore_python_option, pep582_option, verbose_option
from pdm.cli.utils import ErrorArgumentParser, PdmFormatter
from pdm.compat import importlib_metadata
from pdm.exceptions import PdmArgumentError, PdmUsageError
from pdm.installers import InstallManager, Synchronizer
from pdm.models.repositories import PyPIRepository
from pdm.project import Project
from pdm.project.config import Config, ConfigItem
from pdm.utils import is_in_zipapp

COMMANDS_MODULE_PATH = importlib.import_module("pdm.cli.commands").__path__


class Core:
    """A high level object that manages all classes and configurations"""

    parser: argparse.ArgumentParser
    subparsers: argparse._SubParsersAction

    project_class = Project
    repository_class = PyPIRepository
    resolver_class = Resolver
    synchronizer_class = Synchronizer
    install_manager_class = InstallManager

    def __init__(self) -> None:
        self.version = __version__
        self.ui = termui.UI()
        self.init_parser()
        self.load_plugins()

    def init_parser(self) -> None:
        self.parser = ErrorArgumentParser(
            prog="pdm",
            description=__doc__,
            formatter_class=PdmFormatter,
        )
        self.parser.is_root = True  # type: ignore[attr-defined]
        self.parser.add_argument(
            "-V",
            "--version",
            action="version",
            version="{}, version {}".format(
                termui.style("PDM", style="bold"),
                termui.style(self.version, style="success"),
            ),
            help="show the version and exit",
        )
        self.parser.add_argument(
            "-c",
            "--config",
            help="Specify another config file path(env var: PDM_CONFIG_FILE)",
        )
        self.parser._positionals.title = "Commands"
        verbose_option.add_to_parser(self.parser)
        ignore_python_option.add_to_parser(self.parser)
        pep582_option.add_to_parser(self.parser)

        self.subparsers = self.parser.add_subparsers(parser_class=argparse.ArgumentParser)
        for _, name, _ in pkgutil.iter_modules(COMMANDS_MODULE_PATH):
            module = importlib.import_module(f"pdm.cli.commands.{name}", __name__)
            try:
                klass = module.Command
            except AttributeError:
                continue
            self.register_command(klass, klass.name or name)

    def __call__(self, *args: Any, **kwargs: Any) -> None:
        return self.main(*args, **kwargs)

    def ensure_project(self, options: argparse.Namespace, obj: Project | None) -> Project:
        if obj is not None:
            project = obj
        else:
            global_project = bool(getattr(options, "global_project", None))

            default_root = None if global_project or getattr(options, "search_parent", True) else "."
            project = self.create_project(
                getattr(options, "project_path", None) or default_root,
                is_global=global_project,
                global_config=options.config or os.getenv("PDM_CONFIG_FILE"),
            )

        if getattr(options, "lockfile", None):
            project.set_lockfile(options.lockfile)
        return project

    def create_project(
        self,
        root_path: str | Path | None = None,
        is_global: bool = False,
        global_config: str | None = None,
    ) -> Project:
        """Create a new project object

        Args:
            root_path (PathLike): The path to the project root directory
            is_global (bool): Whether the project is a global project
            global_config (str): The path to the global config file

        Returns:
            The project object
        """
        return self.project_class(self, root_path, is_global, global_config)

    def main(
        self,
        args: list[str] | None = None,
        prog_name: str | None = None,
        obj: Project | None = None,
        **extra: Any,
    ) -> None:
        """The main entry function"""
        # Ensure same behavior while testing and using the CLI
        args = args or sys.argv[1:]
        # Keep it for after project parsing to check if its a defined script
        root_script = None
        try:
            options = self.parser.parse_args(args)
        except PdmArgumentError as e:
            # Failed to parse, try to give all to `run` command as shortcut
            # and keep to root script (first non-dashed param) to check existence
            # as soon as the project is parsed
            root_script = next((arg for arg in args if not arg.startswith("-")), None)
            if not root_script:
                self.parser.error(str(e.__cause__))
            try:
                options = self.parser.parse_args(["run", *args])
            except PdmArgumentError as e:
                self.parser.error(str(e.__cause__))

        self.ui.set_verbosity(options.verbose)
        project = self.ensure_project(options, obj)
        self.ui.set_theme(project.global_config.load_theme())
        if options.ignore_python:
            os.environ["PDM_IGNORE_SAVED_PYTHON"] = "1"

        if options.pep582:
            print_pep582_command(project, options.pep582)
            sys.exit(0)

        if root_script and root_script not in project.scripts:
            self.parser.error(f"Command unknown: {root_script}")

        try:
            f = options.handler
        except AttributeError:
            self.parser.print_help(sys.stderr)
            sys.exit(1)
        else:
            try:
                f(project, options)
            except Exception:
                etype, err, traceback = sys.exc_info()
                should_show_tb = not isinstance(err, PdmUsageError)
                if self.ui.verbosity > termui.Verbosity.NORMAL and should_show_tb:
                    raise cast(Exception, err).with_traceback(traceback) from None
                self.ui.echo(
                    rf"[error]\[{etype.__name__}][/]: {err}",  # type: ignore[union-attr]
                    err=True,
                )
                if should_show_tb:
                    self.ui.echo(
                        "Add '-v' to see the detailed traceback",
                        style="warning",
                        err=True,
                    )
                sys.exit(1)
            else:
                if project.config["check_update"] and not is_in_zipapp():
                    check_update(project)

    def register_command(self, command: type[BaseCommand], name: str | None = None) -> None:
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
        entry_points: Iterable[importlib_metadata.EntryPoint] = itertools.chain(
            importlib_metadata.entry_points(group="pdm"),
            importlib_metadata.entry_points(group="pdm.plugin"),
        )
        for plugin in entry_points:
            try:
                plugin.load()(self)
            except Exception as e:
                self.ui.echo(
                    f"Failed to load plugin {plugin.name}={plugin.value}: {e}",
                    style="error",
                    err=True,
                )


def main(args: list[str] | None = None) -> None:
    """The CLI entry function"""
    return Core().main(args)
