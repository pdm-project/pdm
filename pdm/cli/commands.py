import subprocess
import sys

import click
from click._compat import term_len
from click.formatting import HelpFormatter, iter_rows, measure_table, wrap_text
from pdm.cli import actions
from pdm.cli.options import (
    dry_run_option,
    save_strategy_option,
    sections_option,
    update_strategy_option,
    verbose_option,
)
from pdm.context import context
from pdm.project import Project
from pdm.utils import get_user_email_from_git

pass_project = click.make_pass_decorator(Project, ensure=True)
context_settings = {"ignore_unknown_options": True, "allow_extra_args": True}


class ColoredHelpFormatter(HelpFormatter):
    """Click does not provide possibility to replace the inner formatter class
    easily, we have to use monkey patch technique.
    """

    def write_heading(self, heading):
        super().write_heading(context.io.yellow(heading, bold=True))

    def write_dl(self, rows, col_max=30, col_spacing=2):
        rows = list(rows)
        widths = measure_table(rows)
        if len(widths) != 2:
            raise TypeError("Expected two columns for definition list")

        first_col = min(widths[0], col_max) + col_spacing

        for first, second in iter_rows(rows, len(widths)):
            self.write("%*s%s" % (self.current_indent, "", context.io.cyan(first)))
            if not second:
                self.write("\n")
                continue
            if term_len(first) <= first_col - col_spacing:
                self.write(" " * (first_col - term_len(first)))
            else:
                self.write("\n")
                self.write(" " * (first_col + self.current_indent))

            text_width = max(self.width - first_col - 2, 10)
            lines = iter(wrap_text(second, text_width).splitlines())
            if lines:
                self.write(next(lines) + "\n")
                for line in lines:
                    self.write("%*s%s\n" % (first_col + self.current_indent, "", line))
            else:
                self.write("\n")


click.core.HelpFormatter = ColoredHelpFormatter


class PdmGroup(click.Group):
    def main(self, *args, **kwargs):
        # Catches all unhandled exceptions and reraise them with PdmException
        try:
            super().main(*args, **kwargs)
        except Exception:
            etype, err, traceback = sys.exc_info()
            if context.io.verbosity > context.io.NORMAL:
                raise err.with_traceback(traceback)
            else:
                context.io.echo("{}: {}".format(etype.__name__, err), err=True)
                sys.exit(1)


@click.group(cls=PdmGroup)
@verbose_option
@click.version_option(
    prog_name=context.io._style("pdm", bold=True), version=context.version
)
def cli():
    """PDM - Python Development Master"""
    pass


@cli.command(help="Lock dependencies.")
@verbose_option
@pass_project
def lock(project):
    actions.do_lock(project)


@cli.command(help="Install dependencies from lock file.")
@verbose_option
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
@verbose_option
@click.argument("command")
@click.argument("args", nargs=-1)
@pass_project
def run(project, command, args):
    with project.environment.activate():
        expanded_command = project.environment.which(command)
        if not expanded_command:
            raise click.UsageError(
                "Command {} is not found on your PATH.".format(
                    context.io.green(f"'{command}'")
                )
            )
        sys.exit(subprocess.call([expanded_command] + list(args)))


@cli.command(help="Synchronizes current working set with lock file.")
@verbose_option
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
@verbose_option
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
@click.option(
    "-e",
    "editables",
    multiple=True,
    help="Specify editable packages.",
    metavar="EDITABLES",
)
@click.argument("packages", nargs=-1)
@pass_project
def add(project, dev, section, sync, save, strategy, editables, packages):
    actions.do_add(project, dev, section, sync, save, strategy, editables, packages)


@cli.command(help="Update packages in pyproject.toml")
@verbose_option
@sections_option
@update_strategy_option
@save_strategy_option
@click.option(
    "-u",
    "--unconstrained",
    is_flag=True,
    default=False,
    help="Ignore the version constraint of packages.",
)
@click.argument("packages", nargs=-1)
@pass_project
def update(project, dev, sections, default, strategy, save, unconstrained, packages):
    actions.do_update(
        project, dev, sections, default, strategy, save, unconstrained, packages
    )


@cli.command(help="Remove packages from pyproject.toml")
@verbose_option
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


@cli.command(name="list")
@verbose_option
@click.option(
    "--graph", is_flag=True, default=False, help="Display a graph of dependencies."
)
@pass_project
def list_(project, graph):
    """List packages installed in the current working set."""
    actions.do_list(project, graph)


@cli.command(help="Build artifacts for distribution.")
@verbose_option
@click.option(
    "--no-sdist",
    "sdist",
    default=True,
    flag_value=False,
    help="Don't build source tarballs.",
)
@click.option(
    "--no-wheel", "wheel", default=True, flag_value=False, help="Don't build wheels."
)
@click.option("-d", "--dest", default="dist", help="Target directory to put artifacts.")
@click.option(
    "--no-clean",
    "clean",
    default=True,
    flag_value=False,
    help="Do not clean the target directory.",
)
@pass_project
def build(project, sdist, wheel, dest, clean):
    actions.do_build(project, sdist, wheel, dest, clean)


@cli.command(help="Initialize a pyproject.toml for PDM.")
@verbose_option
@pass_project
def init(project):
    if project.pyproject_file.exists():
        context.io.echo(
            "{}".format(
                context.io.cyan("pyproject.toml already exists, update it now.")
            )
        )
    else:
        context.io.echo(
            "{}".format(context.io.cyan("Creating a pyproject.toml for PDM..."))
        )
    name = click.prompt(f"Project name", default=project.root.name)
    version = click.prompt("Project version", default="0.0.0")
    license = click.prompt("License(SPDX name)", default="MIT")

    git_user, git_email = get_user_email_from_git()
    author = click.prompt(f"Author name", default=git_user)
    email = click.prompt(f"Author email", default=git_email)
    actions.do_init(project, name, version, license, author, email)


@cli.command()
@click.argument("python")
@pass_project
def use(project, python):
    """Use the given python version as base interpreter."""
    actions.do_use(project, python)


@cli.command()
@click.option("-p", "--python", is_flag=True, help="Show the interpreter path.")
@click.option(
    "-d", "--project", "show_project", is_flag=True, help="Show the project root path."
)
@click.option("--env", is_flag=True, help="Show PEP508 environment markers.")
@pass_project
def info(project, python, show_project, env):
    """Show the project information."""
    actions.do_info(project, python, show_project, env)
