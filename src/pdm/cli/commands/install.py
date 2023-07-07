import argparse
import sys

from pdm import termui
from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.filters import GroupSelection
from pdm.cli.hooks import HookManager
from pdm.cli.options import dry_run_option, groups_group, install_group, lockfile_option, skip_option, venv_option
from pdm.project import Project


class Command(BaseCommand):
    """Install dependencies from lock file"""

    arguments = (
        *BaseCommand.arguments,
        groups_group,
        install_group,
        dry_run_option,
        lockfile_option,
        skip_option,
        venv_option,
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--no-lock",
            dest="lock",
            action="store_false",
            default=True,
            help="Don't do lock if the lock file is not found or outdated",
        )
        parser.add_argument(
            "--check",
            action="store_true",
            help="Check if the lock file is up to date and fail otherwise",
        )
        parser.add_argument("--plugins", action="store_true", help="Install the plugins specified in pyproject.toml")

    def install_plugins(self, project: Project) -> None:
        from pdm.environments import PythonEnvironment
        from pdm.installers.core import install_requirements
        from pdm.models.requirements import parse_requirement

        plugins = [
            parse_requirement(r[3:], True) if r.startswith("-e ") else parse_requirement(r)
            for r in project.pyproject.plugins
        ]
        if not plugins:
            return
        plugin_root = project.root / ".pdm-plugins"
        environment = PythonEnvironment(project, python=sys.executable, prefix=str(plugin_root))
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
            if options.lock:
                project.core.ui.echo("Updating the lock file...", style="success", err=True)
                unseleted = GroupSelection(project)
                actions.do_lock(
                    project,
                    strategy=strategy,
                    dry_run=options.dry_run,
                    hooks=hooks,
                    # We would like to keep the selected groups when the lockfile exists
                    # but use the groups passed-in when creating a new lockfile.
                    groups=unseleted.all() if strategy != "all" else selection.all(),
                )

        actions.do_sync(
            project,
            selection=selection,
            no_editable=options.no_editable,
            no_self=options.no_self,
            dry_run=options.dry_run,
            fail_fast=options.fail_fast,
            hooks=hooks,
        )
