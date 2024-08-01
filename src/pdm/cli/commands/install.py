import argparse
import sys
import sysconfig

from pdm import termui
from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.filters import GroupSelection
from pdm.cli.hooks import HookManager
from pdm.cli.options import (
    dry_run_option,
    frozen_lockfile_option,
    groups_group,
    install_group,
    lockfile_option,
    override_option,
    skip_option,
    venv_option,
)
from pdm.project import Project


class Command(BaseCommand):
    """Install dependencies from lock file"""

    arguments = (
        *BaseCommand.arguments,
        groups_group,
        install_group,
        override_option,
        dry_run_option,
        lockfile_option,
        frozen_lockfile_option,
        skip_option,
        venv_option,
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--check",
            action="store_true",
            help="Check if the lock file is up to date and fail otherwise",
        )
        parser.add_argument("--plugins", action="store_true", help="Install the plugins specified in pyproject.toml")

    def install_plugins(self, project: Project) -> None:
        from pdm.environments import PythonEnvironment
        from pdm.installers.core import install_requirements
        from pdm.models.requirements import parse_line

        plugins = [parse_line(r) for r in project.pyproject.plugins]
        if not plugins:
            return
        plugin_root = project.root / ".pdm-plugins"
        extra_paths = list({sysconfig.get_path("purelib"), sysconfig.get_path("platlib")})
        environment = PythonEnvironment(
            project, python=sys.executable, prefix=str(plugin_root), extra_paths=extra_paths
        )
        with project.core.ui.open_spinner("[success]Installing plugins...[/]"):
            with project.core.ui.logging("install-plugins"):
                install_requirements(
                    plugins, environment, clean=True, use_install_cache=project.config["install.cache"]
                )
            if not plugin_root.joinpath(".gitignore").exists():
                plugin_root.mkdir(exist_ok=True)
                plugin_root.joinpath(".gitignore").write_text("*\n")
        project.core.ui.echo("Plugins are installed successfully into [primary].pdm-plugins[/].")

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        if not project.pyproject.is_valid and termui.is_interactive():
            actions.ask_for_import(project)

        if options.plugins:
            return self.install_plugins(project)

        hooks = HookManager(project, options.skip)

        strategy = actions.check_lockfile(project, False)
        selection = GroupSelection.from_options(project, options)
        if strategy:
            if options.check:
                project.core.ui.echo(
                    "Please run [success]`pdm lock`[/] to update the lock file",
                    err=True,
                )
                sys.exit(1)
            if project.enable_write_lockfile:
                project.core.ui.echo("Updating the lock file...", style="success", err=True)
            # We would like to keep the selected groups when the lockfile exists
            # but use the groups passed-in when creating a new lockfile or doing a non-lock install.
            if strategy == "all" or not project.enable_write_lockfile:
                lock_selection = selection
            else:
                lock_selection = GroupSelection(project)
            actions.do_lock(
                project,
                strategy=strategy,
                dry_run=options.dry_run,
                hooks=hooks,
                groups=lock_selection.all(),
            )

        actions.do_sync(
            project,
            selection=selection,
            no_editable=options.no_editable,
            no_self=options.no_self or "default" not in selection,
            dry_run=options.dry_run,
            fail_fast=options.fail_fast,
            hooks=hooks,
        )
