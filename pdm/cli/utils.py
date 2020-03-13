from __future__ import annotations

import argparse

import cfonts

from packaging.specifiers import SpecifierSet
from pdm.iostream import stream
from pdm.models.candidates import identify
from pdm.models.environment import WorkingSet
from pdm.models.requirements import Requirement, strip_extras
from pdm.resolver.structs import DirectedGraph


class PdmFormatter(argparse.HelpFormatter):
    def _format_action(self, action):
        # determine the required width and the entry label
        help_position = min(self._action_max_length + 2, self._max_help_position)
        help_width = max(self._width - help_position, 11)
        action_width = help_position - self._current_indent - 2
        action_header = self._format_action_invocation(action)

        # no help; start on same line and add a final newline
        if not action.help:
            tup = self._current_indent, "", action_header
            action_header = "%*s%s\n" % tup

        # short action name; start on the same line and pad two spaces
        elif len(action_header) <= action_width:
            tup = self._current_indent, "", action_width, action_header
            action_header = "%*s%-*s  " % tup
            indent_first = 0

        # long action name; start on the next line
        else:
            tup = self._current_indent, "", action_header
            action_header = "%*s%s\n" % tup
            indent_first = help_position

        # collect the pieces of the action help
        parts = [stream.cyan(action_header)]

        # if there was help for the action, add lines of help text
        if action.help:
            help_text = self._expand_help(action)
            help_lines = self._split_lines(help_text, help_width)
            parts.append("%*s%s\n" % (indent_first, "", help_lines[0]))
            for line in help_lines[1:]:
                parts.append("%*s%s\n" % (help_position, "", line))

        # or add a newline if the description doesn't end with one
        elif not action_header.endswith("\n"):
            parts.append("\n")

        # if there are any sub-actions, add their help as well
        for subaction in self._iter_indented_subactions(action):
            parts.append(self._format_action(subaction))

        # return a single string
        return self._join_parts(parts)


class PdmParser(argparse.ArgumentParser):
    def format_help(self):
        formatter = self._get_formatter()
        formatter.io = stream
        if getattr(self, "is_root", False):
            banner = (
                cfonts.render(
                    "PDM",
                    font="slick",
                    gradient=["bright_red", "bright_green"],
                    space=False,
                )
                + "\n"
            )
            formatter._add_item(lambda x: x, [banner])
            self._positionals.title = "Commands"
        self._optionals.title = "Options"
        # description
        formatter.add_text(self.description)

        # usage
        formatter.add_usage(
            self.usage,
            self._actions,
            self._mutually_exclusive_groups,
            prefix=stream.yellow("Usage", bold=True) + ": ",
        )

        # positionals, optionals and user-defined groups
        for action_group in self._action_groups:
            formatter.start_section(
                stream.yellow(action_group.title, bold=True)
                if action_group.title
                else None
            )
            formatter.add_text(action_group.description)
            formatter.add_arguments(action_group._group_actions)
            formatter.end_section()

        # epilog
        formatter.add_text(self.epilog)
        # determine help from format above
        return formatter.format_help()


class Package:
    """An internal class for the convenience of dependency graph building."""

    def __init__(self, name, version, requirements):
        self.name = name
        self.version = version  # if version is None, the dist is not installed.
        self.requirements = requirements

    def __hash__(self):
        return hash(self.name)

    def __repr__(self):
        return f"<Package {self.name}=={self.version}>"

    def __eq__(self, value):
        return self.name == value.name


def build_dependency_graph(working_set: WorkingSet) -> DirectedGraph:
    """Build a dependency graph from locked result."""
    graph = DirectedGraph()
    graph.add(None)  # sentinel parent of top nodes.
    node_with_extras = set()

    def add_package(key, dist):
        name, extras = strip_extras(key)
        extras = extras or ()
        reqs = {}
        if dist:
            requirements = [
                Requirement.from_pkg_requirement(r) for r in dist.requires(extras)
            ]
            for req in requirements:
                reqs[identify(req)] = req
            version = dist.version
        else:
            version = None

        node = Package(key, version, reqs)
        if node not in graph:
            if extras:
                node_with_extras.add(name)
            graph.add(node)

            for k in reqs:
                child = add_package(k, working_set.get(strip_extras(k)[0]))
                graph.connect(node, child)

        return node

    for k, dist in working_set.items():
        add_package(k, dist)
    for node in graph._vertices.copy():
        if node is not None and not list(graph.iter_parents(node)):
            # Top requirements
            if node.name in node_with_extras:
                # Already included in package[extra], no need to keep the top level
                # non-extra package.
                graph.remove(node)
            else:
                graph.connect(None, node)
    return graph


LAST_CHILD = "└── "
LAST_PREFIX = "    "
NON_LAST_CHILD = "├── "
NON_LAST_PREFIX = "│   "


def format_package(
    graph: DirectedGraph,
    package: Package,
    required: str = "",
    prefix: str = "",
    visited=None,
) -> str:
    """Format one package.

    :param graph: the dependency graph
    :param package: the package instance
    :param required: the version required by its parent
    :param prefix: prefix text for children
    :param visited: the visited package collection
    """
    if visited is None:
        visited = set()
    result = []
    version = (
        stream.red("[ not installed ]")
        if not package.version
        else stream.red(package.version)
        if required
        and required != "Any"
        and not SpecifierSet(required).contains(package.version)
        else stream.yellow(package.version)
    )
    if package.name in visited:
        version = stream.red("[circular]")
    required = f"[ required: {required} ]" if required else ""
    result.append(f"{stream.green(package.name, bold=True)} {version} {required}\n")
    if package.name in visited:
        return "".join(result)
    visited.add(package.name)
    try:
        *children, last = sorted(graph.iter_children(package), key=lambda p: p.name)
    except ValueError:  # No children nodes
        pass
    else:
        for child in children:
            required = str(package.requirements[child.name].specifier or "Any")
            result.append(
                prefix
                + NON_LAST_CHILD
                + format_package(
                    graph, child, required, prefix + NON_LAST_PREFIX, visited.copy()
                )
            )
        required = str(package.requirements[last.name].specifier or "Any")
        result.append(
            prefix
            + LAST_CHILD
            + format_package(
                graph, last, required, prefix + LAST_PREFIX, visited.copy()
            )
        )
    return "".join(result)


def format_dependency_graph(graph: DirectedGraph) -> str:
    """Format dependency graph for output."""
    content = []
    for package in graph.iter_children(None):
        content.append(format_package(graph, package, prefix="", visited=set()))
    return "".join(content).strip()
