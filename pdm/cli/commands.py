import os
import shutil
import subprocess

import click
from pdm.cli import actions
from pdm.cli.options import (
    dry_run_option,
    save_strategy_option,
    sections_option,
    update_strategy_option,
)
from pdm.exceptions import CommandNotFound
from pdm.project import Project

pass_project = click.make_pass_decorator(Project, ensure=True)
context_settings = {"ignore_unknown_options": True, "allow_extra_args": True}


@click.group(help="PDM - Python Development Master")
@click.version_option(prog_name="pdm", version="0.0.1")
def cli():
    pass


@cli.command(help="Lock dependencies.")
@pass_project
def lock(project):
    actions.do_lock(project)


@cli.command(help="Install dependencies from lock file.")
@sections_option
@click.option(
    "--no-lock",
    "lock",
    flag_value=False,
    default=True,
    help="Don't do lock if lockfile is not found or outdated.",
)
@pass_project
def install(project, sections, dev, default, lock):
    if lock and not (
        project.lockfile_file.is_file() and project.is_lockfile_hash_match()
    ):
        actions.do_lock(project)
    actions.do_sync(project, sections, dev, default, False, False)


@cli.command(
    help="Run commands or scripts with local packages loaded.",
    context_settings=context_settings,
)
@click.argument("command")
@click.argument("args", nargs=-1)
@pass_project
def run(project, command, args):
    with project.environment.activate():
        expanded_command = shutil.which(command, path=os.getenv("PATH"))
        if not expanded_command:
            raise CommandNotFound(command)
        subprocess.run([expanded_command] + list(args))


@cli.command(help="Synchronizes current working set with lock file.")
@sections_option
@dry_run_option
@click.option(
    "--clean/--no-clean",
    "clean",
    default=None,
    help="Whether to remove unneeded packages from working set.",
)
@pass_project
def sync(project, sections, dev, default, dry_run, clean):
    actions.do_sync(project, sections, dev, default, dry_run, clean)


@cli.command(help="Add packages to pyproject.toml and install them.")
@click.option(
    "-d",
    "--dev",
    default=False,
    is_flag=True,
    help="Add packages into dev dependencies.",
)
@click.option("-s", "--section", help="Specify target section to add into.")
@click.option(
    "--no-sync",
    "sync",
    flag_value=False,
    default=True,
    help="Only write pyproject.toml and do not sync the working set.",
)
@save_strategy_option
@update_strategy_option
@click.option("-e", "editables", multiple=True, help="Specify editable packages.")
@click.argument("packages", nargs=-1)
@pass_project
def add(project, dev, section, sync, save, strategy, editables, packages):
    actions.do_add(project, dev, section, sync, save, strategy, editables, packages)


@cli.command(help="Update packages in pyproject.toml")
@sections_option
@update_strategy_option
@click.argument("packages", nargs=-1)
@pass_project
def update(project, dev, sections, default, strategy, packages):
    actions.do_update(project, dev, sections, default, strategy, packages)


@cli.command(help="Remove packages from pyproject.toml")
@click.option(
    "-d",
    "--dev",
    default=False,
    is_flag=True,
    help="Remove packages from dev dependencies.",
)
@click.option("-s", "--section", help="Specify target section the package belongs to")
@click.option(
    "--no-sync",
    "sync",
    flag_value=False,
    default=True,
    help="Only write pyproject.toml and do not uninstall packages.",
)
@click.argument("packages", nargs=-1)
@pass_project
def remove(project, dev, section, sync, packages):
    actions.do_remove(project, dev, section, sync, packages)
