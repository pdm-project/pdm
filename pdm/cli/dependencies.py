from __future__ import annotations

from packaging.specifiers import SpecifierSet
from pdm.context import context
from pdm.models.candidates import identify
from pdm.models.environment import WorkingSet
from pdm.models.requirements import Requirement, strip_extras
from pdm.resolver.structs import DirectedGraph


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
    graph: DirectedGraph, package: Package, required: str = "", prefix: str = ""
) -> str:
    """Format one package.

    :param graph: the dependency graph.
    :param package: the package instance.
    :param required: the version required by its parent.
    :param prefix: prefix text for children.
    """
    result = []
    version = (
        context.io.red("[ not installed ]")
        if not package.version
        else context.io.red(package.version)
        if required
        and required != "Any"
        and not SpecifierSet(required).contains(package.version)
        else context.io.yellow(package.version)
    )
    required = f"[ required: {required} ]" if required else ""
    result.append(f"{context.io.green(package.name, bold=True)} {version} {required}\n")
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
                + format_package(graph, child, required, prefix + NON_LAST_PREFIX)
            )
        required = str(package.requirements[last.name].specifier or "Any")
        result.append(
            prefix
            + LAST_CHILD
            + format_package(graph, last, required, prefix + LAST_PREFIX)
        )
    return "".join(result)


def format_dependency_graph(graph: DirectedGraph) -> str:
    """Format dependency graph for output."""
    content = []
    for package in graph.iter_children(None):
        content.append(format_package(graph, package, prefix=""))
    return "".join(content).strip()
