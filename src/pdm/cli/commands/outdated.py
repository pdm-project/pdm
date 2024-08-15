from __future__ import annotations

import functools
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from fnmatch import fnmatch
from itertools import zip_longest
from typing import TYPE_CHECKING

from pdm.cli.commands.base import BaseCommand
from pdm.cli.utils import normalize_pattern
from pdm.models.requirements import strip_extras
from pdm.utils import normalize_name

if TYPE_CHECKING:
    from argparse import ArgumentParser, Namespace

    from unearth import PackageFinder

    from pdm.project.core import Project


@dataclass
class ListPackage:
    package: str
    installed_version: str
    pinned_version: str
    latest_version: str = ""


@functools.lru_cache
def _find_first_diff(a: str, b: str) -> int:
    a_parts = a.split(".")
    b_parts = b.split(".")
    for i, (x, y) in enumerate(zip_longest(a_parts, b_parts)):
        if x != y:
            return (len(".".join(a_parts[:i])) + 1) if i > 0 else 0
    return 0


class Command(BaseCommand):
    """Check for outdated packages and list the latest versions on indexes."""

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--json", action="store_const", const="json", dest="format", default="table", help="Output in JSON format"
        )
        parser.add_argument("patterns", nargs="*", help="The packages to check", type=normalize_pattern)

    @staticmethod
    def _match_pattern(name: str, patterns: list[str]) -> bool:
        return not patterns or any(fnmatch(name, p) for p in patterns)

    @staticmethod
    def _populate_latest_version(finder: PackageFinder, package: ListPackage) -> None:
        best = finder.find_best_match(package.package).best
        if best:
            package.latest_version = best.version or ""

    @staticmethod
    def _format_json(packages: list[ListPackage]) -> str:
        return json.dumps([asdict(package) for package in packages], indent=2)

    @staticmethod
    def _render_version(version: str, base_version: str) -> str:
        from packaging.version import InvalidVersion

        from pdm.utils import parse_version

        if not version or version == base_version:
            return version
        if not base_version:
            return f"[bold red]{version}[/]"

        try:
            parsed_version = parse_version(version)
            parsed_base_version = parse_version(base_version)
        except InvalidVersion:
            return version
        first_diff = _find_first_diff(version, base_version)
        head, tail = version[:first_diff], version[first_diff:]
        if parsed_version.major != parsed_base_version.major:
            return f"{head}[bold red]{tail}[/]"
        if parsed_version.minor != parsed_base_version.minor:
            return f"{head}[bold yellow]{tail}[/]"
        return f"{head}[bold green]{tail}[/]"

    def handle(self, project: Project, options: Namespace) -> None:
        environment = project.environment
        installed = environment.get_working_set()
        resolved = {strip_extras(k)[0]: v for k, v in project.get_locked_repository().candidates.items()}

        collected: list[ListPackage] = []

        for name, distribution in installed.items():
            if not self._match_pattern(name, options.patterns):
                continue
            if project.name and name == normalize_name(project.name):
                continue
            constrained_version = resolved.pop(name).version or "" if name in resolved else ""
            collected.append(ListPackage(name, distribution.version or "", constrained_version))

        for name, candidate in resolved.items():
            if not self._match_pattern(name, options.patterns):
                continue
            if candidate.req.marker and not candidate.req.marker.matches(environment.spec):
                continue
            collected.append(ListPackage(name, "", candidate.version or ""))

        with environment.get_finder() as finder, ThreadPoolExecutor() as executor:
            for package in collected:
                executor.submit(self._populate_latest_version, finder, package)

        collected = sorted(
            [p for p in collected if p.latest_version and p.latest_version != p.installed_version],
            key=lambda p: p.package,
        )
        if options.format == "json":
            print(self._format_json(collected))
        else:
            rows = [
                (
                    package.package,
                    package.installed_version,
                    self._render_version(package.pinned_version, package.installed_version),
                    self._render_version(package.latest_version, package.installed_version),
                )
                for package in collected
            ]
            project.core.ui.display_columns(rows, header=["Package", "Installed", "Pinned", "Latest"])
