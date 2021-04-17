import argparse
from pathlib import Path

from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import sections_group
from pdm.cli.utils import compatible_dev_flag, translate_sections
from pdm.formats import FORMATS
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
            "--pyproject",
            action="store_true",
            help="Read the list of packages from pyproject.toml",
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        candidates = {}
        sections = list(options.sections)
        if options.pyproject:
            options.hashes = False
        sections = translate_sections(
            project,
            options.default,
            compatible_dev_flag(project, options.dev),
            options.sections or (),
        )
        for section in sections:
            if options.pyproject:
                candidates.update(project.get_dependencies(section))
            else:
                candidates.update(project.get_locked_candidates(section))
        candidates.pop(project.meta.name and project.meta.project_name, None)

        content = FORMATS[options.format].export(project, candidates.values(), options)
        if options.output:
            Path(options.output).write_text(content)
        else:
            project.core.ui.echo(content)
