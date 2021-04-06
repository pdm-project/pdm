import argparse
import os

from pdm import termui
from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import verbose_option
from pdm.exceptions import PdmUsageError
from pdm.models.pip_shims import directory_size, file_size, find_files
from pdm.project import Project


class Command(BaseCommand):
    """Control the caches of PDM"""

    arguments = [verbose_option]

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        subparsers = parser.add_subparsers()
        ClearCommand.register_to(subparsers, "clear")
        RemoveCommand.register_to(subparsers, "remove")
        ListCommand.register_to(subparsers, "list")
        InfoCommand.register_to(subparsers, "info")
        self.parser = parser

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        self.parser.print_help()


def format_size(size: int) -> str:
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

    if pattern == "*":
        files = list(find_files(project.cache_dir, pattern))
    else:
        # Only remove wheel files which specific pattern is given
        files = list(find_files(project.cache("wheels"), pattern))

    if not files:
        raise PdmUsageError("No matching files found")

    for file in files:
        os.unlink(file)
        project.core.ui.echo(f"Removed {file}", verbosity=termui.DETAIL)
    project.core.ui.echo(f"{len(files)} file{'s' if len(files) > 1 else ''} removed")


class ClearCommand(BaseCommand):
    """Clean all the files under cache directory"""

    arguments = [verbose_option]
    CACHE_TYPES = ("hashes", "http", "wheels", "metadata")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("type", nargs="?", help="Clear the given type of caches")

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        if not options.type:
            cache_parent = project.cache_dir
        elif options.type not in self.CACHE_TYPES:
            raise PdmUsageError(
                f"Invalid cache type {options.type}, should one of {self.CACHE_TYPES}"
            )
        else:
            cache_parent = project.cache(options.type)

        with project.core.ui.open_spinner(
            f"Clearing {options.type or 'all'} caches..."
        ) as spinner:
            files = list(find_files(cache_parent, "*"))
            for file in files:
                os.unlink(file)
            spinner.succeed(f"{len(files)} file{'s' if len(files) > 1 else ''} removed")


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
        rows = [
            (format_size(file_size(file)), os.path.basename(file))
            for file in find_files(project.cache("wheels"), options.pattern)
        ]
        project.core.ui.display_columns(rows, [">Size", "Filename"])


class InfoCommand(BaseCommand):
    """Show the info and current size of caches"""

    arguments = [verbose_option]

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        with project.core.ui.open_spinner("Calculating cache files") as spinner:
            output = [
                f"{termui.cyan('Cache Root')}: {project.cache_dir}, "
                f"Total size: {format_size(directory_size(project.cache_dir))}"
            ]
            for name, description in [
                ("hashes", "File Hashe Cache"),
                ("http", "HTTP Cache"),
                ("wheels", "Wheels Cache"),
                ("metadata", "Metadata Cache"),
            ]:
                cache_location = project.cache(name)
                files = list(find_files(cache_location, "*"))
                size = directory_size(cache_location)
                output.append(f"  {termui.cyan(description)}: {cache_location}")
                output.append(f"    Files: {len(files)}, Size: {format_size(size)}")
            spinner.stop_and_persist("\n".join(output))
