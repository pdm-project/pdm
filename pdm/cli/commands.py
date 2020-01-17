import os
import shutil
import subprocess

import click
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
@pass_project
def install(project, sections, dev, default):
    candidates = set()
    if default:
        candidates.update(project.get_locked_candidates())
    if dev:
        candidates.update(project.get_locked_candidates("dev"))
    for section in sections:
        candidates.update(project.get_locked_candidates(section))
    installer = project.get_installer()
    for can in candidates:
        installer.install_candidate(can)


@cli.command(
    help="Run commands or scripts with local packages loaded.",
    context_settings=context_settings
)
@click.argument("command")
@click.argument("args", nargs=-1)
@pass_project
def run(project, command, args):
    with project.environment.activate():
        command = shutil.which(command, path=os.getenv("PATH"))
        subprocess.run([command] + list(args))
