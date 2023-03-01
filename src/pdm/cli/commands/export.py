from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from pdm.cli.actions import resolve_candidates_from_lockfile
from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import groups_group, lockfile_option
from pdm.cli.utils import translate_groups
from pdm.exceptions import PdmUsageError
from pdm.formats import FORMATS
from pdm.models.candidates import Candidate
from pdm.models.requirements import Requirement
from pdm.project import Project


class Command(BaseCommand):
    """Export the locked packages set to other formats"""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        lockfile_option.add_to_parser(parser)
        parser.add_argument(
            "-f",
            "--format",
            choices=FORMATS.keys(),
            default="requirements",
            help="Specify the export file format",
        )
        groups_group.add_to_parser(parser)
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
        groups: list[str] = list(options.groups)
        if options.pyproject:
            options.hashes = False
        groups = translate_groups(
            project,
            options.default,
            options.dev,
            options.groups or (),
        )
        requirements: dict[str, Requirement] = {}
        packages: Iterable[Requirement] | Iterable[Candidate]
        for group in groups:
            requirements.update(project.get_dependencies(group))
        if options.pyproject:
            packages = requirements.values()
        else:
            if not project.lockfile.exists:
                raise PdmUsageError("No lockfile found, please run `pdm lock` first.")
            project.core.ui.echo(
                "The exported requirements file is no longer cross-platform. "
                "Using it on other platforms may cause unexpected result.",
                style="warning",
                err=True,
            )
            candidates = resolve_candidates_from_lockfile(project, requirements.values())
            # Remove candidates with [extras] because the bare candidates are already
            # included
            packages = (candidate for candidate in candidates.values() if not candidate.req.extras)

        content = FORMATS[options.format].export(project, packages, options)
        if options.output:
            Path(options.output).write_text(content)
        else:
            project.core.ui.echo(content)
