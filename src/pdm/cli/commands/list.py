from __future__ import annotations

import argparse
import csv
import io
import json
from collections import defaultdict
from typing import Iterable, Mapping, Sequence

from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.utils import (
    DirectedGraph,
    Package,
    build_dependency_graph,
    check_project_file,
    get_dist_location,
    show_dependency_graph,
)
from pdm.compat import importlib_metadata as im
from pdm.exceptions import PdmUsageError
from pdm.models.requirements import Requirement
from pdm.project import Project

# Group label for subdependencies
SUBDEP_GROUP_LABEL = ":sub"


class Command(BaseCommand):
    """List packages installed in the current working set"""

    DEFAULT_FIELDS = "name,version,location"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        graph = parser.add_mutually_exclusive_group()

        parser.add_argument(
            "--freeze",
            action="store_true",
            help="Show the installed dependencies in pip's requirements.txt format",
        )

        graph.add_argument("--graph", action="store_true", help="Display a graph of dependencies")

        parser.add_argument("-r", "--reverse", action="store_true", help="Reverse the dependency graph")

        parser.add_argument(
            "--resolve",
            action="store_true",
            default=False,
            help="Resolve all requirements to output licenses (instead of just showing those currently installed)",
        )

        parser.add_argument(
            "--fields",
            default=Command.DEFAULT_FIELDS,
            help="Select information to output as a comma separated string. "
            "For example: name,version,homepage,licenses,groups.",
        )

        parser.add_argument(
            "--sort",
            default=None,
            help="Sort the output using a given field name. If nothing is "
            "set, no sort is applied. Multiple fields can be combined with ','.",
        )

        list_formats = parser.add_mutually_exclusive_group()

        list_formats.add_argument(
            "--csv",
            action="store_true",
            help="Output dependencies in CSV document format",
        )

        list_formats.add_argument(
            "--json",
            action="store_true",
            help="Output dependencies in JSON document format",
        )

        list_formats.add_argument(
            "--markdown",
            action="store_true",
            help="Output dependencies and legal notices in markdown document format - best effort basis",
        )

        parser.add_argument(
            "--include",
            default="",
            help="Dependency groups to include in the output. By default all are included",
        )

        parser.add_argument(
            "--exclude",
            default="",
            help="Exclude dependency groups from the output",
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        # Raise an error if the project is not defined.
        check_project_file(project)

        # Freeze.
        if options.freeze:
            self.hande_freeze(project, options)
            return

        # Map dependency groups to requirements.
        name_to_groups: Mapping[str, set[str]] = defaultdict(set)
        for g in project.iter_groups():
            for k in project.get_dependencies(g):
                if "[" in k:
                    k = k.split("[")[0]
                name_to_groups[k].add(g)

        # Set up `--include` and `--exclude` dep groups.
        # Include everything by default (*) then exclude after.
        # Check to make sure that only valid dep group names are given.
        valid_groups = {*list(project.iter_groups()), SUBDEP_GROUP_LABEL}
        include = set(parse_comma_separated_string(options.include, lowercase=False, asterisk_values=valid_groups))
        if not all(g in valid_groups for g in include):
            raise PdmUsageError(f"--include groups must be selected from: {valid_groups}")
        exclude = set(parse_comma_separated_string(options.exclude, lowercase=False, asterisk_values=valid_groups))
        if exclude and not all(g in valid_groups for g in exclude):
            raise PdmUsageError(f"--exclude groups must be selected from: {valid_groups}")

        # Include selects only certain groups when set, but always selects :sub
        # unless it is explicitly unset.
        selected_groups = include if include else valid_groups
        selected_groups = selected_groups | {SUBDEP_GROUP_LABEL}
        selected_groups = selected_groups - (exclude - include)

        # Requirements as importtools distributions (eg packages).
        # Resolve all the requirements. Map the candidates to distributions.
        requirements = [
            r for g in selected_groups if g != SUBDEP_GROUP_LABEL for r in project.get_dependencies(g).values()
        ]
        if options.resolve:
            candidates = actions.resolve_candidates_from_lockfile(project, requirements)
            packages: Mapping[str, im.Distribution] = {
                k: c.prepare(project.environment).metadata for k, c in candidates.items()
            }

        # Use requirements from the working set (currently installed).
        else:
            packages = project.environment.get_working_set()

        selected_keys = {r.identify() for r in requirements}
        dep_graph = build_dependency_graph(
            packages,
            project.environment.marker_environment,
            None if not (include or exclude) else selected_keys,
            include_sub=SUBDEP_GROUP_LABEL in selected_groups,
        )

        # Process as a graph or list.
        if options.graph:
            self.handle_graph(dep_graph, project, options)
        else:
            selected_packages = [k.name.split("[")[0] for k in dep_graph if k]
            packages = {k: v for k, v in packages.items() if k in selected_packages}
            self.handle_list(packages, name_to_groups, project, options)

    def hande_freeze(self, project: Project, options: argparse.Namespace) -> None:
        if options.graph:
            raise PdmUsageError("--graph cannot be used with --freeze")
        if options.reverse:
            raise PdmUsageError("--reverse cannot be used without --graph")
        if options.fields != Command.DEFAULT_FIELDS:
            raise PdmUsageError("--fields cannot be used with --freeze")
        if options.resolve:
            raise PdmUsageError("--resolve cannot be used with --freeze")
        if options.sort:
            raise PdmUsageError("--sort cannot be used with --freeze")
        if options.csv:
            raise PdmUsageError("--csv cannot be used with --freeze")
        if options.json:
            raise PdmUsageError("--json cannot be used with --freeze")
        if options.markdown:
            raise PdmUsageError("--markdown cannot be used with --freeze")
        if options.include or options.exclude:
            raise PdmUsageError("--include/--exclude cannot be used with --freeze")

        working_set = project.environment.get_working_set()
        requirements = sorted(
            (Requirement.from_dist(dist).as_line() for dist in working_set.values()),
            key=lambda x: x.lower(),
        )
        project.core.ui.echo("\n".join(requirements))

    def handle_graph(
        self,
        dep_graph: DirectedGraph[Package | None],
        project: Project,
        options: argparse.Namespace,
    ) -> None:
        if options.csv:
            raise PdmUsageError("--csv cannot be used with --graph")
        if options.markdown:
            raise PdmUsageError("--markdown cannot be used with --graph")
        if options.sort:
            raise PdmUsageError("--sort cannot be used with --graph")

        show_dependency_graph(project, dep_graph, reverse=options.reverse, json=options.json)

    def handle_list(
        self,
        packages: Mapping[str, im.Distribution],
        name_to_groups: Mapping[str, set[str]],
        project: Project,
        options: argparse.Namespace,
    ) -> None:
        if options.reverse:
            raise PdmUsageError("--reverse cannot be used without --graph")

        # Check the fields are specified OK.
        fields = parse_comma_separated_string(options.fields, asterisk_values=Listable.KEYS)
        if not all(field in Listable.KEYS for field in fields):
            raise PdmUsageError(f"--fields must specify one or more of: {Listable.KEYS}")

        # Wrap each distribution with a Listable (and a groups pairing)
        # to make it easier to filter on later.
        def _group_of(name: str) -> set[str]:
            return name_to_groups.get(name, {SUBDEP_GROUP_LABEL})

        records = [Listable(d, _group_of(k)) for k, d in packages.items()]
        ui = project.core.ui

        # Order based on a field key.
        if options.sort:
            keys = parse_comma_separated_string(options.sort)
            if not all(key in Listable.KEYS for key in keys):
                raise PdmUsageError(f"--sort key must be one of: {','.join(Listable.KEYS)}")
            records.sort(key=lambda d: tuple(d[key] for key in keys))

        # Write CSV
        if options.csv:
            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=fields)
            writer.writeheader()
            for row in records:
                writer.writerow(row.json(fields))
            ui.echo(buffer.getvalue(), highlight=True, end="")

        # Write JSON
        elif options.json:
            json_row = [row.json(fields) for row in records]
            ui.echo(json.dumps(json_row, indent=4), highlight=True)

        # Write Markdown
        elif options.markdown:
            body = [f"# {project.name} licenses"]
            body.extend(row.markdown(fields) for row in records)
            text_body = "\n".join(body)
            try:
                ui.echo(text_body, highlight=True)
            except UnicodeEncodeError:
                ui.echo(
                    "Markdown output contains non-ASCII characters. "
                    "Setting env var PYTHONIOENCODING to 'utf8' may fix this.",
                    err=True,
                    style="error",
                )
                ui.echo(text_body.encode().decode("ascii", errors="ignore"), highlight=True)
                ui.echo("**Problem decoding file as UTF-8.  Some characters may be omit.**")

        # Write nice table format.
        else:
            formatted = [row.rich(fields) for row in records]
            ui.display_columns(formatted, fields)


def parse_comma_separated_string(
    comma_string: str,
    lowercase: bool = True,
    asterisk_values: Iterable[str] | None = None,
) -> list[str]:
    """Parse a CLI comma separated string.
    Apply optional lowercase transformation and if the value given is "*" then
    return a list of pre-defined values (`asterisk_values`).
    """
    if asterisk_values is not None and comma_string.strip() == "*":
        return list(asterisk_values)
    items = f"{comma_string}".split(",")
    items = [el.strip() for el in items if el]
    if lowercase:
        items = [el.lower() for el in items]
    return items


class Listable:
    """Wrapper makes sorting and exporting information about a Distribution
    easier.  It also retrieves license information from dist-info metadata.

    https://packaging.python.org/en/latest/specifications/core-metadata
    """

    # Fields that users are allowed to sort on.
    KEYS = frozenset(["name", "groups", "version", "homepage", "licenses", "location"])

    def __init__(self, dist: im.Distribution, groups: set[str]):
        self.dist = dist

        self.name: str | None = dist.metadata["Name"]
        self.groups = "|".join(groups)

        self.version: str | None = dist.metadata["Version"]
        self.version = None if self.version == "UNKNOWN" else self.version

        self.homepage: str | None = dist.metadata["Home-Page"]
        self.homepage = None if self.homepage == "UNKNOWN" else self.homepage

        # If the License metadata field is empty or UNKNOWN then try to
        # find the license in the Trove classifiers.  There may be more than one
        # so generate a pipe separated list (to avoid complexity with CSV export).
        self.licenses: str | None = dist.metadata["License"]
        self.licenses = None if self.licenses == "UNKNOWN" else self.licenses
        if not self.licenses:
            classifier_licenses = [v for v in dist.metadata.get_all("Classifier", []) if v.startswith("License")]
            alternatives = [parts.split("::") for parts in classifier_licenses]
            alternatives = [part[-1].strip() for part in alternatives if part]
            self.licenses = "|".join(alternatives)

    @property
    def location(self) -> str:
        return get_dist_location(self.dist)

    def license_files(self) -> list[im.PackagePath]:
        """Path to files inside the package that may contain license information
        or other legal notices.

        The implementation is a "best effort" and may contain errors, select
        incorrect information, or otherwise be error-prone. It is not a
        substitute for a lawyer.
        """
        if not self.dist.files:
            return []

        # Inconsistency between packages means that we check in several locations
        # for license files.  There may be 0 or more of these.  There may be false
        # positives & negatives.
        locations = ("**/LICENSE*", "**/LICENCE*", "**/COPYING*", "**/NOTICE*")

        # Compile a list of all file paths in the distribution that look like
        # they might contain a license file.
        paths = []
        for path in self.dist.files:
            paths += [path for loc in locations if path.match(loc)]
        return paths

    def __getitem__(self, field: str) -> str:
        if field not in Listable.KEYS:
            raise PdmUsageError(f"list field `{field}` not in: {Listable.KEYS}")
        return getattr(self, field)

    def json(self, fields: Sequence[str]) -> dict:
        return {f: self[f] for f in fields}

    def rich(self, fields: Sequence[str]) -> Sequence[str]:
        output = []
        for field in fields:
            data = f"{self[field]}"
            data = data if field != "name" else f"[req]{data}[/]"
            data = data if field != "version" else f"[warning]{data}[/]"
            data = data if field != "groups" else f"[error]{data}[/]"
            output.append(data)
        return output

    def markdown(self, fields: Sequence[str]) -> str:
        nl = "\n"
        section = ""

        # Heading
        section += f"## {self.name}{nl}"
        section += f"{nl}"

        # Table
        section += f"| Name | {self.name} |{nl}"
        section += f"|----|----|{nl}"
        for field in fields:
            if field == "name":
                continue
            section += f"| {field.capitalize()} | {self[field]} |{nl}"
        section += f"{nl}"

        # Files
        for path in self.license_files():
            section += f"{path}{nl}"
            section += f"{nl}{nl}"
            section += f"````{nl}"
            try:
                section += path.read_text("utf-8")
            except UnicodeDecodeError:
                section += "Problem decoding file as UTF-8"
            except Exception as err:
                section += f"Problem finding license text: {err}"
            section += f"{nl}"
            section += f"````{nl}"
            section += f"{nl}"
        return section
