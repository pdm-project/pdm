from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from pdm.cli.commands.base import BaseCommand
from pdm.cli.filters import GroupSelection
from pdm.cli.options import groups_group, lockfile_option
from pdm.exceptions import PdmUsageError
from pdm.formats import FORMATS
from pdm.models.candidates import Candidate
from pdm.models.requirements import Requirement
from pdm.project import Project
from pdm.project.lockfile import FLAG_INHERIT_METADATA


class Command(BaseCommand):
    """Export the locked packages set to other formats"""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        lockfile_option.add_to_parser(parser)
        parser.add_argument(
            "-f",
            "--format",
            choices=["requirements"],
            default="requirements",
            help="Only requirements.txt is supported for now.",
        )
        groups_group.add_to_parser(parser)
        parser.add_argument(
            "--no-hashes",
            "--without-hashes",
            dest="hashes",
            action="store_false",
            default=True,
            help="Don't include artifact hashes",
        )
        parser.add_argument(
            "--no-markers",
            action="store_false",
            default=True,
            dest="markers",
            help="(DEPRECATED)Don't include platform markers",
        )
        parser.add_argument(
            "--no-extras", action="store_false", default=True, dest="extras", help="Strip extras from the requirements"
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
        parser.add_argument("--expandvars", action="store_true", help="Expand environment variables in requirements")
        group = parser.add_mutually_exclusive_group()
        group.add_argument("--self", action="store_true", help="Include the project itself")
        group.add_argument(
            "--editable-self", action="store_true", help="Include the project itself as an editable dependency"
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        if options.pyproject:
            options.hashes = False
        selection = GroupSelection.from_options(project, options)
        if options.markers is False:
            project.core.ui.deprecated("The --no-markers option is deprecated and has no effect.")
        packages: Iterable[Requirement] | Iterable[Candidate]
        if options.pyproject:
            packages = [r for group in selection for r in project.get_dependencies(group)]
        else:
            if not project.lockfile.exists():
                raise PdmUsageError("No lockfile found, please run `pdm lock` first.")
            if FLAG_INHERIT_METADATA not in project.lockfile.strategy:
                raise PdmUsageError(
                    "Can't export a lock file without environment markers, please re-generate the lock file with `inherit_metadata` strategy."
                )
            candidates = sorted(
                (entry.candidate for entry in project.get_locked_repository().packages.values()),
                key=lambda c: not c.req.extras,
            )
            groups = set(selection)
            packages = []
            seen_extras: set[str] = set()
            for candidate in candidates:
                if groups.isdisjoint(candidate.req.groups):
                    continue
                if options.extras:
                    key = candidate.req.key or ""
                    if candidate.req.extras:
                        seen_extras.add(key)
                    elif key in seen_extras:
                        continue
                elif candidate.req.extras:
                    continue
                packages.append(candidate)  # type: ignore[arg-type]

        content = FORMATS[options.format].export(project, packages, options)
        if options.output:
            Path(options.output).write_text(content, encoding="utf-8")
        else:
            # Use a regular print to avoid any formatting / wrapping.
            print(content)
