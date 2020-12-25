import argparse

from pip._vendor.pkg_resources import safe_name

from pdm.cli.commands.base import BaseCommand
from pdm.iostream import stream
from pdm.models.candidates import Candidate
from pdm.models.project_info import ProjectInfo
from pdm.models.requirements import parse_requirement
from pdm.project import Project


def normalize_package(name):
    return safe_name(name).lower()


def filter_stable(candidate: Candidate) -> bool:
    return not candidate.version.is_prerelease


class Command(BaseCommand):
    """Show the package information"""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "package",
            type=normalize_package,
            help="Specify the package name",
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:

        package = options.package
        req = parse_requirement(package)
        repository = project.get_repository()
        # reverse the result so that latest is at first.
        matches = repository.find_candidates(
            req, project.environment.python_requires, True
        )
        latest = next(iter(matches), None)
        if not latest:
            stream.echo(
                stream.yellow(f"No match found for the package {package!r}"), err=True
            )
            return
        latest_stable = next(filter(filter_stable, matches), None)
        installed = project.environment.get_working_set().get(package)

        metadata = latest.get_metadata()
        if metadata._legacy:
            result = ProjectInfo(dict(metadata._legacy.items()), True)
        else:
            result = ProjectInfo(dict(metadata._data), False)
        if latest_stable:
            result.latest_stable_version = str(latest_stable.version)
        if installed:
            result.installed_version = str(installed.version)

        stream.display_columns(list(result.generate_rows()))
