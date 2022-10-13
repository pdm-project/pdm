import json
import argparse
from collections import defaultdict

from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.utils import check_project_file
from pdm.compat import Distribution
from pdm.project import Project


# BUG: displaying coloured text can break certain package printouts
# for example: "cachecontrol[filecache]"


# TODO:
# Build a graph so we can work out which packages are used by others..
# dep_graph = build_dependency_graph(
#     working_set, project.environment.marker_environment
# )
# show_dependency_graph(project, dep_graph, reverse=reverse, json=json)

class LicenseLookup:
    """ Tool to help finding licence information within package dist-info
    and metadata.
    """
    def __init__(self, identifier: str, dist: Distribution):
        self.identifier = identifier
        self.dist = dist

    @property
    def name(self):
        return self.dist.metadata.get("Name", None)

    @property
    def version(self):
        return self.dist.metadata.get("Version", None)

    def licenses(self, comma=","):
        """ Comma separated list of license names.

        Typically, returns the `License` field specified in the dist-info metadata.
        If this is not available or UNKNOWN, then the last part of the
        Trove "Classifier :: License :: ..." strings are returned as a comma separated list.

        https://packaging.python.org/en/latest/specifications/core-metadata/#license
        """
        meta = self.dist.metadata.get("License", None)
        if meta == "UNKNOWN" or meta is None:
            alternatives = [parts.split("::") for parts in self.classifier_licences()]
            alternatives = [part[-1].strip() for part in alternatives if part]
            return comma.join(alternatives)
        return meta

    def classifier_licences(self):
        """ Find all `Classifier: License ::` entries in the dist-info metadata.
        """
        for k, v in self.dist.metadata.items():
            if (k == "Classifier" and v.startswith("License")):
                yield v

    @property
    def homepage(self):
        """ `Home-page` as specified in the dist-info metadata.
        https://packaging.python.org/en/latest/specifications/core-metadata/#home-page """
        # TODO: load from Project-URL instead?
        data = self.dist.metadata.get("Home-Page", None)
        data = None if data == "UNKNOWN" else data
        return data
    
    def find_license_files(self):
        """ Find and return the paths to all files in the dist-info that might
        contain license information or other legal notices.

        This is not exhaustive, may contain zero or more files, and may offer
        files that do not contain legal information.
        """
        # Check to see if there is a "License-File" metadata string.
        # meta = self.dist.metadata.get("License-File", None)
        # if meta:
        #     return [meta]

        # If the distribution is not local, it may not have files.
        if not self.dist.files:
            return []

        # Inconsistency between packages means that we check in several locations
        # for license files.  There may be 0 or more of these.  There may be false
        # positives & negatives.
        locations = ("**/LICENSE*", "**/LICENCE*", "**/COPYING*", "**/NOTICE*")

        # Compile a list of all file paths in the distribution that look like
        # they might contain a license file.
        licenses = []
        for path in self.dist.files:
            licenses += [path for loc in locations if path.match(loc)]
        return licenses

    def as_record(self, **kwargs):
        # TODO: add classifier_licences
        return {
            "identifier": self.identifier,
            "name": self.name,
            "version": self.version,
            "homepage": self.homepage,
            "licenses": self.licenses(),
            "files": self.find_license_files(),
            **kwargs
        }


class Command(BaseCommand):
    """List package licences installed in the current working set"""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        group = parser.add_mutually_exclusive_group()

        parser.add_argument('--fields',
            default="identifier,version,licenses,group,homepage",
            # action="store_const",
            help="Select information to output as a comma separated string. "\
                 "For example: identifier,name,version,homepage,licenses,group." \
                 "The `group` field is not used in --working mode."
        )

        group.add_argument(
            "--resolve",
            action="store_true",
            default=False,
            help="Resolve all requirements to output licenses (instead of just showing those currently installed)",
        )

        parser.add_argument(
            "--skip",
            default="",
            help="Do not export this comma separated list of named groups (see [tool.pdm.dev-dependencies]). " \
                 "For example: `test,doc,default`",
        )

        parser.add_argument(
            "--sort",
            default=None,
            help="Sort the output using a given field. If nothing is set, no sort is applied.",
        )

        parser.add_argument(
            "--csv",
            action="store_true",
            help="Output the installed licences in CSV format",
        )

        parser.add_argument(
            "--json",
            action="store_true",
            help="Output the installed licences in JSON document format",
        )

        parser.add_argument(
            "--markdown",
            action="store_true",
            help="Output the installed licences and license texts in markdown document format",
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:

        check_project_file(project)

        # Parse a list of comma separated strings.
        def _parse_list(css):
            items = f"{css}".split(",")
            items = [el.strip() for el in items if el]
            return items
        
        # Fields to output and groups to skip.
        fields = _parse_list(options.fields)
        skip = set(_parse_list(options.skip))

        # Check we had a valid sort field.
        if options.sort:
            fields = ["identifier", "name", "version", "homepage", "licenses"]#, "files"]
            if options.sort not in fields:
                raise KeyError(f"sort key `{options.sort}` is not a valid field ({fields})")


        def _format_table(record, fields):
            """ Output as a PDM table (consistent colours) """
            output = []
            for field in fields:
                data = f"{record[field]}"
                data = data if field != "version" else f"[yellow]{data}[/]"
                data = data if field != "identifier" else f"[green]{data}[/]"
                data = data if field != "group" else f"[red]{data}[/]"
                output.append(data)
            return output
        
        def _format_csv(record, fields, comma):
            """ Output as a CSV file """
            output = []
            for field in fields:
                output.append(f"{record[field]}")
            return comma.join(output)
        
        def _format_json(record, fields):
            """ Output as JSON dicts. """
            filtered = {k: v for k, v in record.items() if k in fields}
            if "files" in filtered:
                raise NotImplementedError()
            return filtered

        def _format_markdown(record):
            """ Output as a section in a markdown file """
            s = ""
            s += f"## {record['identifier']}\n"
            s += "\n"
            s += f"| Name | {record['name']} |\n"
            s += "|---|---|\n"
            s += f"| Version | {record['version']} |\n"
            s += f"| Licenses | {record['licenses']} |\n"
            s += f"| Homepage | {record['homepage']} |\n"
            s += f"| Dep Groups | {record['group']} |\n"  ## BUG NOT WORKING
            s += "\n"
            for path in record["files"]:
                s += str(path)
                s += "\n\n"
                s += "````\n"
                try:
                    lic = path.read_text()
                    s += lic
                except Exception as err:
                    s += f"Problem finding license text: {err} \n"
                s += "\n````\n"
                s += "\n"
            return s

        # Export the working set of packages (ie. those that are installed).
        if not options.resolve:
            working_set = project.environment.get_working_set()
            output = [LicenseLookup(k, d).as_record(group="") for k, d in working_set.items()]

        # Otherwise resolve all the requirements based on the lockfile.
        else:
            # List all explicitly defined requirements and map each to a list of
            # groups that contains it (eg. test, doc).
            requires = set()
            groups = defaultdict(set)
            for group in project.iter_groups():
                packages = project.get_dependencies(group).values()
                for pkg in packages:
                    groups[pkg.identify()].add(group)
                    requires.add(pkg)

            # Resolve distributions for all specified requirements and then
            # remap these to the groups that they were defined in. If a requirement
            # has no group, then its likely a sub-dependency.
            # NOTE: Different requirement combinations can lead the resolver to
            # select different versions. If a package license changes between versions,
            # then the reported license may be different to the one that is distributed.
            candidates = actions.resolve_candidates_from_lockfile(project, requires)
            
            # Prepare distributions for each candidate so we can get the data we need.
            # Use a table to merge duplicates.
            distributions = {}
            for candidate in candidates.values():
                prepared = candidate.prepare(project.environment)
                dist = prepared.metadata
                identifier = prepared.req.identify()
                group = groups.get(identifier, set(("sub", )))
                distributions[identifier] = dist, group

            # Find the licenses for each one and produce a record for export.
            output = []
            for identifier, pair in distributions.items():
                dist, groups = pair
                if skip.intersection(groups):
                    continue
                group = " & ".join(groups)
                output.append(LicenseLookup(identifier, dist).as_record(group=group))

        # Sort.
        if options.sort:
            output.sort(key=lambda record: record.get(options.sort))

        # Write CSV file to console.
        if options.csv:
            comma = ","
            print(comma.join(fields))
            for row in output:
                print(_format_csv(row, fields, comma))

        # Write JSON output.
        elif options.json:
            formatted = [_format_json(r, fields) for r in output]
            print(json.dumps(formatted, indent=4))

        # Write Markdown output.
        elif options.markdown:
            print(f"# {project.name} licences")
            for row in output:
                try:
                    print(_format_markdown(row))
                except UnicodeEncodeError:
                    print(_format_markdown(row).encode().decode("ascii", errors="ignore"))
                    print("A UnicodeEncodeError was encountered.  Some characters may be omit.")

        # Write fancy table output.
        else:
            # BUG: displaying coloured text can break certain package printouts
            # for example: "cachecontrol[filecache]"
            formatted = [_format_table(r, fields) for r in output]
            project.core.ui.display_columns(formatted, fields)
