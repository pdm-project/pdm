from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from pdm.cli.actions import resolve_candidates_from_lockfile
from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import sections_group
from pdm.cli.utils import translate_sections
from pdm.formats import FORMATS
from pdm.models.candidates import Candidate
from pdm.models.requirements import Requirement
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
        sections: list[str] = list(options.sections)
        if options.pyproject:
            options.hashes = False
        sections = translate_sections(
            project,
            options.default,
            options.dev,
            options.sections or (),
        )
        requirements: dict[str, Requirement] = {}
        packages: Iterable[Requirement] | Iterable[Candidate]
        for section in sections:
            requirements.update(project.get_dependencies(section))
        if options.pyproject:
            packages = requirements.values()
        else:
            project.core.ui.echo(
                "The exported requirements file is no longer cross-platform. "
                "Using it on other platforms may cause unexpected result.",
                fg="yellow",
                err=True,
            )
            candidates = resolve_candidates_from_lockfile(
                project, requirements.values()
            )
            packages = candidates.values()

        content = FORMATS[options.format].export(
            project, packages, options
        )  # type: ignore
        if options.output:
            Path(options.output).write_text(content)
        else:
            project.core.ui.echo(content)
