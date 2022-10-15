import argparse
import json
from collections import defaultdict
from importlib.metadata import Distribution
from typing import Dict, List, Set

from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.utils import (
    build_dependency_graph,
    check_project_file,
    get_dist_location,
    show_dependency_graph,
)
from pdm.exceptions import PdmUsageError
from pdm.project import Project


# Group label for subdependencies
SUBDEP_GROUP_LABEL = ":sub"


class Command(BaseCommand):
    """List packages installed in the current working set"""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        graph = parser.add_mutually_exclusive_group()

        graph.add_argument(
            "--graph", action="store_true", help="Display a graph of dependencies"
        )
        parser.add_argument(
            "-r", "--reverse", action="store_true", help="Reverse the dependency graph"
        )

        parser.add_argument(
            "--resolve",
            action="store_true",
            default=False,
            help="Resolve all requirements to output licenses (instead of just showing those currently installed)",
        )

        parser.add_argument(
            "--fields",
            default="name,version,location",
            help="Select information to output as a comma separated string. "
            "For example: name,version,homepage,licenses,group.",
        )

        parser.add_argument(
            "--sort",
            default=None,
            help="Sort the output using a given field name. If nothing is set, no sort is applied.",
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
            default="*",
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

        # Map dependency groups to requirements.
        name_to_groups = defaultdict(set)
        for g in project.iter_groups():
            for r in project.get_dependencies(g).values():
                name_to_groups[r.name].add(g)

        # Set up `--include` and `--exclude` dep groups.
        # Include everything by default (*) then exclude after.
        # Check to make sure that only valid dep group names are given.
        valid_groups = [g for g in project.iter_groups()] + [SUBDEP_GROUP_LABEL]
        include = parse_comma_separated_string(options.include, lowercase=False, asterisk_values=valid_groups)
        if not all(g in valid_groups for g in include):
            raise PdmUsageError(f"--include groups names must be selected from: {valid_groups}")
        exclude = parse_comma_separated_string(options.exclude, lowercase=False)
        if exclude and not all(g in valid_groups for g in exclude):
            raise PdmUsageError(f"--exclude groups names must be selected from: {valid_groups}")
        selected_groups = set(g for g in include if g not in exclude)

        # Requirements as importtools distributions (eg packages).
        # Resolve all the requirements. Map the candidates to distributions.
        if options.resolve:
            requirements = [
                r
                for g in project.iter_groups()
                for r in project.get_dependencies(g).values()
            ]
            candidates = actions.resolve_candidates_from_lockfile(project, requirements)
            packages = set(
                c.prepare(project.environment).metadata for c in candidates.values()
            )
            packages = {p.metadata["Name"]: p for p in packages}

        # Use requirements from the working set (currently installed).
        else:
            packages = project.environment.get_working_set()
            packages = {p.metadata["Name"]: p for p in packages.values()}

        # Filter the set of packages to show by --include and --exclude
        group_of = lambda d: name_to_groups.get(d.metadata["Name"], set((SUBDEP_GROUP_LABEL, )))
        group_in = lambda d: any(g in selected_groups for g in group_of(d))
        packages = {d.metadata["Name"]: d for d in packages.values() if group_in(d)}

        # Process as a graph or list.
        if options.graph:
            self.handle_graph(packages, project, options)
        else:
            self.handle_list(packages, name_to_groups, project, options)
            # self.handle_list(packages, name_to_groups, selected_groups, project, options)

    def handle_graph(self,
                     packages: Dict[str, Distribution],
                     project: Project,
                     options: argparse.Namespace) -> None:
        if options.csv:
            raise PdmUsageError("--csv cannot be used with --graph")
        if options.markdown:
            raise PdmUsageError("--markdown cannot be used with --graph")
        if options.sort:
            raise PdmUsageError("--sort cannot be used with --graph")

        dep_graph = build_dependency_graph(
            packages, project.environment.marker_environment
        )
        show_dependency_graph(project, dep_graph, reverse=options.reverse, json=options.json)
    
    def handle_list(self,
                    packages: Dict[str, Distribution],
                    name_to_groups: Dict[str, Set[str]],
                    # selected_groups: Set[str],
                    project: Project,
                    options: argparse.Namespace) -> None:
        if options.reverse:
            raise PdmUsageError("--reverse cannot be used without --graph")

        # Check the fields are specified OK.
        fields = parse_comma_separated_string(
            options.fields, asterisk_values=Listable.KEYS
        )
        if not all(field in Listable.KEYS for field in fields):
            raise PdmUsageError(
                f"--fields must specify one or more of: {Listable.KEYS}"
            )

        # Wrap each distribution with a Listable (and a groups pairing) to make it easier
        # to filter on later.
        group_of = lambda d: name_to_groups.get(d.metadata["Name"], set((SUBDEP_GROUP_LABEL, )))
        records = [Listable(d, group_of(d)) for d in packages.values()]

        # Order based on a field key.
        if options.sort:
            key = options.sort.lower()
            if key not in Listable.KEYS:
                raise PdmUsageError(f"--sort key must be one of: {Listable.KEYS}")
            records.sort(key=lambda d: getattr(d, options.sort.lower()))

        # Write CSV
        if options.csv:
            comma = ","
            print(comma.join(fields))
            for row in records:
                print(row.csv(fields, comma=comma))

        # Write JSON
        elif options.json:
            formatted = [row.json(fields) for row in records]
            print(json.dumps(formatted, indent=4))

        # Write Markdown
        elif options.markdown:
            print(f"# {project.name} licences")
            for row in records:
                section = row.markdown(fields)
                try:
                    print(section)
                except UnicodeEncodeError:
                    print(section.encode().decode("ascii", errors="ignore"))
                    print(
                        "A UnicodeEncodeError was encountered.  Some characters may be omit."
                    )

        # Write nice table format.
        else:
            formatted = [row.pdm(fields) for row in records]
            project.core.ui.display_columns(formatted, fields)


def parse_comma_separated_string(comma_string, lowercase=True, asterisk_values=None):
    """Parse a CLI comma separated string.
    Apply optional lowercase transformation and if the value given is "*" then
    return a list of pre-defined values (`asterisk_values`).
    """
    if asterisk_values and comma_string.strip() == "*":
        return asterisk_values
    items = f"{comma_string}".split(",")
    items = [el.strip() for el in items if el]
    if lowercase:
        items = [el.lower() for el in items]
    return items


class Listable:
    """Wrapper makes sorting and exporting information about a Distribution
    a little easier.  It also does some common work to retrieve information
    about licenses from dist-info metadata.

    https://packaging.python.org/en/latest/specifications/core-metadata
    """

    # Fields that users are allowed to sort on.
    KEYS = ["name", "groups", "version", "homepage", "licenses", "location"]

    def __init__(self, dist: Distribution, groups: Set[str]):
        self.dist = dist

        self.name = dist.metadata.get("Name", None)
        self.groups = "|".join(groups)

        self.version = dist.metadata.get("Version", None)
        self.version = None if self.version == "UNKNOWN" else self.version

        self.homepage = dist.metadata.get("Home-Page", None)
        self.homepage = None if self.homepage == "UNKNOWN" else self.homepage

        # If the License metadata field is empty or UNKNOWN then try to
        # find the license in the Trove classifers.  There may be more than one
        # so generate a pipe separated list (to avoid complexity with CSV export).
        self.licenses = dist.metadata.get("License", None)
        self.licenses = None if self.licenses == "UNKNOWN" else self.licenses
        if not self.licenses:
            classifier_licenses = [
                v
                for k, v in dist.metadata.items()
                if k == "Classifier" and v.startswith("License")
            ]
            alternatives = [parts.split("::") for parts in classifier_licenses]
            alternatives = [part[-1].strip() for part in alternatives if part]
            self.licenses = "|".join(alternatives)

    @property
    def location(self):
        return get_dist_location(self.dist)

    def license_files(self):
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

    def __getitem__(self, field):
        if field not in Listable.KEYS:
            raise PdmUsageError(f"list field `{field}` not in: {Listable.KEYS}")
        return getattr(self, field)

    def csv(self, fields: List[str], comma: str):
        return comma.join(f"{self[field]}" for field in fields)

    def json(self, fields):
        return {f: self[f] for f in fields}

    def pdm(self, fields):
        output = []
        for field in fields:
            data = f"{self[field]}"
            data = data if field != "name" else f"[green]{data}[/]"
            data = data if field != "version" else f"[yellow]{data}[/]"
            data = data if field != "groups" else f"[red]{data}[/]"
            output.append(data)
        return output

    def markdown(self, fields: List[str]):
        nl = "\n"
        section = ""

        # Heading
        section += f"## {self.name}{nl}"
        section += f"{nl}"

        # Table
        section += f"| Name | {self.name} | {nl}"
        section += f"|----|----|{nl}"
        for field in fields:
            if field == "name":
                continue
            section += f"| {field.capitalize()} | {self[field]} | {nl}"
        section += f"{nl}"

        # Files
        for path in self.license_files():
            section += f"{path}{nl}"
            section += f"{nl}{nl}"
            section += f"````{nl}"
            try:
                section += path.read_text()
            except Exception as err:
                s += f"Problem finding license text: {err}"
            section += f"{nl}"
            section += f"````{nl}"
            section += f"{nl}"
        return section
