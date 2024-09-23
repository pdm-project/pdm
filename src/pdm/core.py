r"""
    ____  ____  __  ___
   / __ \/ __ \/  |/  /
  / /_/ / / / / /|_/ /
 / ____/ /_/ / /  / /
/_/   /_____/_/  /_/
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses as dc
import importlib
import itertools
import os
import pkgutil
import sys
from datetime import datetime
from functools import cached_property
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, cast

import tomlkit.exceptions

from pdm import termui
from pdm.__version__ import __version__
from pdm.cli.options import ignore_python_option, no_cache_option, non_interactive_option, pep582_option, verbose_option
from pdm.cli.utils import ArgumentParser, ErrorArgumentParser
from pdm.compat import importlib_metadata
from pdm.exceptions import PdmArgumentError, PdmUsageError
from pdm.installers import InstallManager
from pdm.models.repositories import BaseRepository, PyPIRepository
from pdm.project import Project
from pdm.project.config import Config
from pdm.utils import is_in_zipapp

if TYPE_CHECKING:
    from typing import Any, Iterable

    from pdm.cli.commands.base import BaseCommand
    from pdm.project.config import ConfigItem

COMMANDS_MODULE_PATH = importlib.import_module("pdm.cli.commands").__path__


@dc.dataclass
class State:
    """State of the core object."""

    config_settings: dict[str, Any] | None = None
    """The config settings map shared by all packages"""
    exclude_newer: datetime | None = None
    """The exclude newer than datetime for the lockfile"""
    build_isolation: bool = True
    """Whether to make an isolated environment and install requirements for build"""
    enable_cache: bool = True
    """Whether to enable the cache"""
    overrides: list[str] = dc.field(default_factory=list)
    """The requirement overrides for the resolver"""


class Core:
    """A high level object that manages all classes and configurations"""

    parser: argparse.ArgumentParser
    subparsers: argparse._SubParsersAction

    project_class = Project
    repository_class: type[BaseRepository] = PyPIRepository
    install_manager_class = InstallManager

    def __init__(self) -> None:
        self.version = __version__
        self.exit_stack = contextlib.ExitStack()
        self.ui = termui.UI(exit_stack=self.exit_stack)
        self.state = State()
        self.exit_stack.callback(setattr, self, "config_settings", None)
        self.init_parser()
        self.load_plugins()

    def create_temp_dir(self, *args: Any, **kwargs: Any) -> str:
        return self.exit_stack.enter_context(TemporaryDirectory(*args, **kwargs))

    def init_parser(self) -> None:
        self.parser = ErrorArgumentParser(
            prog="pdm",
            description=__doc__,
        )
        self.parser.add_argument(
            "-V",
            "--version",
            action="version",
            version="{}, version {}".format(
                termui.style("PDM", style="bold"),
                termui.style(self.version, style="success"),
            ),
            help="Show the version and exit",
        )
        self.parser.add_argument(
            "-c",
            "--config",
            help="Specify another config file path [env var: PDM_CONFIG_FILE] ",
        )
        verbose_option.add_to_parser(self.parser)
        no_cache_option.add_to_parser(self.parser)
        ignore_python_option.add_to_parser(self.parser)
        pep582_option.add_to_parser(self.parser)
        non_interactive_option.add_to_parser(self.parser)

        self.subparsers = self.parser.add_subparsers(parser_class=ArgumentParser, title="commands", metavar="")
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
        self.state.build_isolation = project.config["build_isolation"]
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

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        """Called before command invocation"""
        from pdm.cli.commands.fix import Command as FixCommand
        from pdm.cli.hooks import HookManager
        from pdm.cli.utils import use_venv

        self.ui.set_verbosity(options.verbose)
        self.ui.set_theme(project.global_config.load_theme())
        self.ui.log_dir = os.path.expanduser(cast(str, project.config["log_dir"]))

        command = cast("BaseCommand | None", getattr(options, "command", None))
        self.state.config_settings = getattr(options, "config_setting", None)

        if options.no_cache:
            self.state.enable_cache = False

        hooks = HookManager(project, getattr(options, "skip", None))
        hooks.try_emit("pre_invoke", command=command.name if command else None, options=options)

        if not isinstance(command, FixCommand):
            FixCommand.check_problems(project)

        for callback in getattr(options, "callbacks", []):
            callback(project, options)

        if lockfile := getattr(options, "lockfile", None):
            project.set_lockfile(cast(str, lockfile))

        if getattr(options, "use_venv", None):
            use_venv(project, cast(str, options.use_venv))

        if overrides := getattr(options, "override", None):
            self.state.overrides = overrides

        if command is None:
            self.parser.print_help()
            sys.exit(0)
        command.handle(project, options)

    @staticmethod
    def get_command(args: list[str]) -> tuple[int, str]:
        """Get the command name from the arguments"""
        options_with_values = ("-c", "--config")
        need_value = False
        for i, arg in enumerate(args):
            if arg.startswith("-"):
                if not arg.startswith(options_with_values):
                    continue
                if (arg.startswith("-c") and arg != "-c") or arg.startswith("--config="):
                    continue
                need_value = True
            elif need_value:
                need_value = False
                continue
            else:
                return i, arg
        return -1, ""

    def _get_cli_args(self, args: list[str], obj: Project | None) -> list[str]:
        project = self.create_project(is_global=False) if obj is None else obj
        if project.is_global:
            return args
        try:
            config = project.pyproject.settings.get("options", {})
        except tomlkit.exceptions.TOMLKitError as e:  # pragma: no cover
            self.ui.error(f"Failed to parse pyproject.toml: {e}")
            config = {}
        (pos, command) = self.get_command(args)
        if command and command in config:
            # add args after the command
            args[pos + 1 : pos + 1] = list(config[command])
        return args

    def main(
        self,
        args: list[str] | None = None,
        prog_name: str | None = None,
        obj: Project | None = None,
        **extra: Any,
    ) -> None:
        """The main entry function"""
        if args is None:
            args = []
        args = self._get_cli_args(args, obj)
        # Keep it for after project parsing to check if its a defined script
        root_script = None
        try:
            options = self.parser.parse_args(args)
        except PdmArgumentError as e:
            # Failed to parse, try to give all to `run` command as shortcut
            # and keep to root script (first non-dashed param) to check existence
            # as soon as the project is parsed
            _, root_script = self.get_command(args)
            if not root_script:
                self.parser.error(str(e.__cause__))
            try:
                options = self.parser.parse_args(["run", *args])
            except PdmArgumentError as e:
                self.parser.error(str(e.__cause__))

        project = self.ensure_project(options, obj)
        if root_script and root_script not in project.scripts:
            self.parser.error(f"Script unknown: {root_script}")

        try:
            self.handle(project, options)
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
                self.ui.warn("Add '-v' to see the detailed traceback", verbosity=termui.Verbosity.NORMAL)
            sys.exit(1)
        else:
            if project.config["check_update"] and not is_in_zipapp():
                from pdm.cli.actions import check_update

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

    def _add_project_plugins_library(self) -> None:
        project = self.create_project(is_global=False)
        if project.is_global or not project.root.joinpath(".pdm-plugins").exists():
            return

        import site
        import sysconfig

        base = str(project.root / ".pdm-plugins")
        replace_vars = {"base": base, "platbase": base}
        scheme = "nt" if os.name == "nt" else "posix_prefix"
        purelib = sysconfig.get_path("purelib", scheme, replace_vars)
        scripts = sysconfig.get_path("scripts", scheme, replace_vars)
        site.addsitedir(purelib)
        if os.path.exists(scripts):
            os.environ["PATH"] = os.pathsep.join([scripts, os.getenv("PATH", "")])

    def load_plugins(self) -> None:
        """Import and load plugins under `pdm.plugin` namespace
        A plugin is a callable that accepts the core object as the only argument.

        Example:
            ```python
            def my_plugin(core: pdm.core.Core) -> None:
                ...
            ```
        """
        self._add_project_plugins_library()
        entry_points: Iterable[importlib_metadata.EntryPoint] = itertools.chain(
            importlib_metadata.entry_points(group="pdm"),
            importlib_metadata.entry_points(group="pdm.plugin"),
        )
        for plugin in entry_points:
            try:
                plugin.load()(self)
            except Exception as e:
                self.ui.error(
                    f"Failed to load plugin {plugin.name}={plugin.value}: {e}",
                )

    @cached_property
    def uv_cmd(self) -> list[str]:
        from pdm.compat import importlib_metadata

        self.ui.info("Using uv is experimental and might break due to uv updates.")
        # First, try to find uv in Python modules
        try:
            importlib_metadata.distribution("uv")
        except ModuleNotFoundError:
            pass
        else:
            return [sys.executable, "-m", "uv"]
        # Try to find it in the typical place:
        if (uv_path := Path.home() / ".cargo/bin/uv").exists():
            return [str(uv_path)]
        # If not found, try to find it in PATH
        import shutil

        path = shutil.which("uv")
        if path:
            return [path]
        # If not found, try to find in the bin dir:
        if (uv_path := Path(sys.argv[0]).with_name("uv")).exists():
            return [str(uv_path)]
        raise PdmUsageError(
            "use_uv is enabled but can't find uv, please install it first: "
            "https://docs.astral.sh/uv/getting-started/installation/"
        )


def main(args: list[str] | None = None) -> None:
    """The CLI entry function"""
    core = Core()
    with core.exit_stack:
        return core.main(args or sys.argv[1:])
