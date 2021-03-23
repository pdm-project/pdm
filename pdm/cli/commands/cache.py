import argparse
import os

from pdm import termui
from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import verbose_option
from pdm.cli.utils import find_files
from pdm.exceptions import PdmUsageError
from pdm.project import Project


class Command(BaseCommand):
    """Control the caches of PDM"""

    arguments = [verbose_option]

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        subparsers = parser.add_subparsers()
        ClearCommand.register_to(subparsers, "clear")
        RemoveCommand.register_to(subparsers, "remove")
        ListCommand.register_to(subparsers, "list")

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        pass


def format_size(size: int) -> int:
    if size > 1000 * 1000:
        return "{:.1f} MB".format(size / 1000.0 / 1000)
    elif size > 10 * 1000:
        return "{} kB".format(int(size / 1000))
    elif size > 1000:
        return "{:.1f} kB".format(size / 1000.0)
    else:
        return "{} bytes".format(int(size))


def remove_cache_files(project: Project, pattern: str) -> None:
    if not pattern:
        raise PdmUsageError("Please provide a pattern")

    files = list(find_files(project.cache("wheels"), pattern))

    if pattern == "*":
        # Only include http files when no specific pattern given
        files.extend(find_files(project.cache("http"), pattern))

    if not files:
        raise PdmUsageError("No matching files found")

    for file in files:
        file.unlink()
        project.core.ui.echo(f"Removed {file}", verbosity=termui.DETAIL)
    project.core.ui.echo(f"{len(files)} file{'s' if len(files) > 1 else ''} removed")


class ClearCommand(BaseCommand):
    """Clean all the files under cache directory"""

    arguments = [verbose_option]

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        return remove_cache_files(project, "*")


class RemoveCommand(BaseCommand):
    """Remove files matching the given pattern"""

    arguments = [verbose_option]

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("pattern", help="The pattern to remove")

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        return remove_cache_files(project, options.pattern)


class ListCommand(BaseCommand):
    """List the built wheels stored in the cache"""

    arguments = [verbose_option]

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "pattern", nargs="?", default="*", help="The pattern to list"
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        rows = []
        for file in find_files(project.cache("wheels"), options.pattern):
            rows.append((format_size(os.path.getsize(file)), file.name))
        project.core.ui.display_columns(rows, [">Size", "Filename"])
