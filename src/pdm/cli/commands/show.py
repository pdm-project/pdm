from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import venv_option
from pdm.exceptions import PdmUsageError
from pdm.models.candidates import Candidate
from pdm.models.project_info import ProjectInfo
from pdm.models.requirements import parse_requirement
from pdm.project import Project
from pdm.utils import normalize_name, parse_version

if TYPE_CHECKING:
    from unearth import Package


def filter_stable(package: Package) -> bool:
    assert package.version
    return not parse_version(package.version).is_prerelease


class Command(BaseCommand):
    """Show the package information"""

    metadata_keys = ("name", "version", "summary", "license", "platform", "keywords")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        venv_option.add_to_parser(parser)
        parser.add_argument(
            "package",
            type=normalize_name,
            nargs=argparse.OPTIONAL,
            help="Specify the package name, or show this package if not given",
        )
        for option in self.metadata_keys:
            parser.add_argument(f"--{option}", action="store_true", help=f"Show {option}")

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        package = options.package
        if package:
            with project.environment.get_finder() as finder:
                best_match = finder.find_best_match(package, allow_prereleases=True)
            if not best_match.applicable:
                project.core.ui.warn(f"No match found for the package {package!r}")
                return
            latest = Candidate.from_installation_candidate(best_match.best, parse_requirement(package))
            latest_stable = next(filter(filter_stable, best_match.applicable), None)
            metadata = latest.prepare(project.environment).metadata
        else:
            if not project.is_distribution:
                raise PdmUsageError("This project is not a library")
            package = normalize_name(project.name)
            metadata = project.make_self_candidate(False).prepare(project.environment).prepare_metadata(True)
            latest_stable = None
        project_info = ProjectInfo.from_distribution(metadata)

        if any(getattr(options, key, None) for key in self.metadata_keys):
            for key in self.metadata_keys:
                if getattr(options, key, None):
                    project.core.ui.echo(getattr(project_info, key))
            return

        installed = project.environment.get_working_set().get(package)
        if latest_stable:
            project_info.latest_stable_version = str(latest_stable.version)
        if installed:
            project_info.installed_version = str(installed.version)
        project.core.ui.display_columns(list(project_info.generate_rows()))
