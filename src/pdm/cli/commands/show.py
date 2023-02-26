import argparse

from packaging.version import Version

from pdm.cli.commands.base import BaseCommand
from pdm.exceptions import PdmUsageError
from pdm.models.candidates import Candidate
from pdm.models.project_info import ProjectInfo
from pdm.models.requirements import parse_requirement
from pdm.project import Project
from pdm.utils import normalize_name


def filter_stable(candidate: Candidate) -> bool:
    assert candidate.version
    return not Version(candidate.version).is_prerelease


class Command(BaseCommand):
    """Show the package information"""

    metadata_keys = ["name", "version", "summary", "license", "platform", "keywords"]

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
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
            req = parse_requirement(package)
            repository = project.get_repository()
            # reverse the result so that latest is at first.
            matches = repository.find_candidates(req, True, True)
            latest = next(iter(matches), None)
            if not latest:
                project.core.ui.echo(
                    f"No match found for the package {package!r}",
                    err=True,
                    style="warning",
                )
                return
            latest_stable = next(filter(filter_stable, matches), None)
            metadata = latest.prepare(project.environment).metadata
            project_info = ProjectInfo.from_distribution(metadata)
        else:
            if not project.name:
                raise PdmUsageError("This project is not a package")
            package = normalize_name(project.name)
            project_info = ProjectInfo.from_metadata(project.pyproject.metadata)
            latest_stable = None

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
