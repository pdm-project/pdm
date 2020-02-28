import shutil

import click

from pdm.cli.options import pass_project
from pdm.context import context


@click.group(name="cache")
def cache_cmd():
    """Control the caches of PDM"""
    pass


@cache_cmd.command()
@pass_project
def clear(project):
    """Clean all the files under cache directory"""
    shutil.rmtree(context.cache_dir, ignore_errors=True)
    context.io.echo("Caches are cleared successfully.")
