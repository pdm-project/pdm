import os
import shutil
import subprocess

import click
from pdm.cli import actions
from pdm.exceptions import CommandNotFound
from pdm.project import Project
from pdm.resolver import lock as _lock

pass_project = click.make_pass_decorator(Project, ensure=True)
context_settings = {
    "ignore_unknown_options": True,
    "allow_extra_args": True
}


@click.group(help="PDM - Python Development Master")
@click.version_option(prog_name="pdm", version="0.0.1")
def cli():
    pass


@cli.command(help="Lock dependencies.")
@pass_project
def lock(project):
    _lock(project)


@cli.command(help="Install dependencies from lock file.")
@click.option(
    "-s", "--section", "sections", multiple=True, help="Specify section(s) to install."
)
@click.option(
    "-d", "--dev", default=False, is_flag=True, help="Also install dev dependencies."
)
@click.option(
    "--no-default", "default", flag_value=False, default=True,
    help="Don't install dependencies from default seciton."
)
@click.option(
    "--no-lock", "lock", flag_value=False, default=True,
    help="Don't do lock if lockfile is not found or outdated."
)
@pass_project
def install(project, sections, dev, default, lock):
    if lock and not (
        project.lockfile_file.is_file() and project.is_lockfile_hash_match()
    ):
        _lock(project)
    actions.do_sync(project, sections, dev, default, False, False)


@cli.command(
    help="Run commands or scripts with local packages loaded.",
    context_settings=context_settings
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
@click.option(
    "-s", "--section", "sections", multiple=True, help="Specify section(s) to install."
)
@click.option(
    "-d", "--dev", default=False, is_flag=True, help="Also install dev dependencies."
)
@click.option(
    "--no-default", "default", flag_value=False, default=True,
    help="Don't install dependencies from default seciton."
)
@click.option(
    "--dry-run", is_flag=True, default=False,
    help="Only prints actions without actually running them."
)
@click.option(
    "--clean/--no-clean", "clean", default=None,
    help="Whether to remove unneeded packages from working set."
)
@pass_project
def sync(project, sections, dev, default, dry_run, clean):
    actions.do_sync(project, sections, dev, default, dry_run, clean)
