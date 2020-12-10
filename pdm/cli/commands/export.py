import argparse
from pathlib import Path

from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import sections_group
from pdm.formats import FORMATS
from pdm.iostream import stream
from pdm.project import Project


class Command(BaseCommand):
    """Export the locked packages set to other formats"""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-f",
            "--format",
            choices=FORMATS.keys(),
            default="requirements",
            help="Specify the export file format",
        )
        sections_group.add_to_parser(parser)
        parser.add_argument(
            "--without-hashes",
            dest="hashes",
            action="store_false",
            default=True,
            help="Don't include artifact hashes",
        )
        parser.add_argument(
            "-o",
            "--output",
            help="Write output to the given file, or print to stdout if not given",
        )
        parser.add_argument(
            "-p",
            "--pyproject",
            action="store_true",
            help="Read the list of packages from pyproject.toml",
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        candidates = []
        if options.pyproject:
            options.hashes = False
        if options.default:
            # Don't include self candidate
            if options.pyproject:
                temp = project.dependencies
            else:
                temp = project.get_locked_candidates()
                temp.pop(project.meta.name, None)
            candidates.extend(temp.values())
        if options.dev:
            if options.pyproject:
                candidates.extend(project.dev_dependencies.values())
            else:
                candidates.extend(project.get_locked_candidates("dev").values())
        for section in options.sections:
            if options.pyproject:
                candidates.extend(project.get_dependencies(section).values())
            else:
                candidates.extend(project.get_locked_candidates(section).values())
        content = FORMATS[options.format].export(project, candidates, options)
        if options.output:
            Path(options.output).write_text(content)
        else:
            stream.echo(content)
