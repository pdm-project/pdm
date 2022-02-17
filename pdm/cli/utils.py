from __future__ import annotations

import argparse
import json
import os
import sys
from argparse import Action, _ArgumentGroup
from collections import ChainMap, OrderedDict
from json import dumps
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable, Mapping, MutableMapping, cast

import tomlkit
from packaging.specifiers import SpecifierSet
from packaging.version import parse as parse_version
from resolvelib.structs import DirectedGraph

from pdm import termui
from pdm._types import Distribution
from pdm.exceptions import PdmUsageError, ProjectError
from pdm.formats import FORMATS
from pdm.formats.base import make_array, make_inline_table
from pdm.models.pip_shims import url_to_path
from pdm.models.requirements import (
    Requirement,
    filter_requirements_with_extras,
    parse_requirement,
    strip_extras,
)
from pdm.models.specifiers import get_specifier
from pdm.models.working_set import WorkingSet
from pdm.project import Project
from pdm.utils import is_path_relative_to

if TYPE_CHECKING:
    from resolvelib.resolvers import RequirementInformation, ResolutionImpossible

    from pdm.models.candidates import Candidate


class PdmFormatter(argparse.HelpFormatter):
    def start_section(self, heading: str | None) -> None:
        return super().start_section(
            termui.yellow(heading.title() if heading else heading, bold=True)
        )

    def _format_usage(
        self,
        usage: str,
        actions: Iterable[Action],
        groups: Iterable[_ArgumentGroup],
        prefix: str | None,
    ) -> str:
        if prefix is None:
            prefix = "Usage: "
        result = super()._format_usage(usage, actions, groups, prefix)
        if prefix:
            return result.replace(prefix, termui.yellow(prefix, bold=True))
        return result

    def _format_action(self, action: Action) -> str:
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
            tup = self._current_indent, "", action_width, action_header  # type: ignore
            action_header = "%*s%-*s  " % tup  # type: ignore
            indent_first = 0

        # long action name; start on the next line
        else:
            tup = self._current_indent, "", action_header  # type: ignore
            action_header = "%*s%s\n" % tup
            indent_first = help_position

        # collect the pieces of the action help
        parts = [termui.cyan(action_header)]

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


class Package:
    """An internal class for the convenience of dependency graph building."""

    def __init__(
        self, name: str, version: str | None, requirements: dict[str, Requirement]
    ) -> None:
        self.name = name
        self.version = version  # if version is None, the dist is not installed.
        self.requirements = requirements

    def __hash__(self) -> int:
        return hash(self.name)

    def __repr__(self) -> str:
        return f"<Package {self.name}=={self.version}>"

    def __eq__(self, value: object) -> bool:
        if not isinstance(value, Package):
            return False
        return self.name == value.name


def build_dependency_graph(
    working_set: WorkingSet, marker_env: dict[str, str] | None = None
) -> DirectedGraph:
    """Build a dependency graph from locked result."""
    graph: DirectedGraph[Package | None] = DirectedGraph()
    graph.add(None)  # sentinel parent of top nodes.
    node_with_extras: set[str] = set()

    def add_package(key: str, dist: Distribution | None) -> Package:
        name, extras = strip_extras(key)
        extras = extras or ()
        reqs: dict[str, Requirement] = {}
        if dist:
            requirements = (
                parse_requirement(r)
                for r in filter_requirements_with_extras(
                    dist.metadata["Name"], dist.requires or [], extras  # type: ignore
                )
            )
            for req in requirements:
                if not req.marker or req.marker.evaluate(marker_env):
                    reqs[req.identify()] = req
            version: str | None = dist.version
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
    for node in list(graph):
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


def specifier_from_requirement(requirement: Requirement) -> str:
    return str(requirement.specifier or "Any")


def format_package(
    graph: DirectedGraph,
    package: Package,
    required: str = "",
    prefix: str = "",
    visited: frozenset[str] = frozenset(),
) -> str:
    """Format one package.

    :param graph: the dependency graph
    :param package: the package instance
    :param required: the version required by its parent
    :param prefix: prefix text for children
    :param visited: the visited package collection
    """
    result = []
    version = (
        termui.red("[ not installed ]")
        if not package.version
        else termui.red(package.version)
        if required
        and required not in ("Any", "This project")
        and not SpecifierSet(required).contains(package.version)
        else termui.yellow(package.version)
    )
    if package.name in visited:
        version = termui.red("[circular]")
    required = f"[ required: {required} ]" if required else "[ Not required ]"
    result.append(f"{termui.green(package.name, bold=True)} {version} {required}\n")
    if package.name in visited:
        return "".join(result)
    children = sorted(graph.iter_children(package), key=lambda p: p.name)
    for i, child in enumerate(children):
        is_last = i == len(children) - 1
        head = LAST_CHILD if is_last else NON_LAST_CHILD
        cur_prefix = LAST_PREFIX if is_last else NON_LAST_PREFIX
        required = specifier_from_requirement(package.requirements[child.name])
        result.append(
            prefix
            + head
            + format_package(
                graph, child, required, prefix + cur_prefix, visited | {package.name}
            )
        )
    return "".join(result)


def format_reverse_package(
    graph: DirectedGraph,
    package: Package,
    child: Package | None = None,
    requires: str = "",
    prefix: str = "",
    visited: frozenset[str] = frozenset(),
) -> str:
    """Format one package for output reverse dependency graph."""
    version = (
        termui.red("[ not installed ]")
        if not package.version
        else termui.yellow(package.version)
    )
    if package.name in visited:
        version = termui.red("[circular]")
    requires = (
        f"[ requires: {termui.red(requires)} ]"
        if requires not in ("Any", "")
        and child
        and child.version
        and not SpecifierSet(requires).contains(child.version)
        else ""
        if not requires
        else f"[ requires: {requires} ]"
    )
    result = [f"{termui.green(package.name, bold=True)} {version} {requires}\n"]
    if package.name in visited:
        return "".join(result)
    parents: list[Package] = sorted(
        filter(None, graph.iter_parents(package)), key=lambda p: p.name
    )
    for i, parent in enumerate(parents):
        is_last = i == len(parents) - 1
        head = LAST_CHILD if is_last else NON_LAST_CHILD
        cur_prefix = LAST_PREFIX if is_last else NON_LAST_PREFIX
        requires = specifier_from_requirement(parent.requirements[package.name])
        result.append(
            prefix
            + head
            + format_reverse_package(
                graph,
                parent,
                package,
                requires,
                prefix + cur_prefix,
                visited | {package.name},
            )
        )
    return "".join(result)


def package_is_project(package: Package, project: Project) -> bool:
    return (
        not project.environment.is_global
        and bool(project.meta.name)
        and package.name == project.meta.project_name.lower()
    )


def _format_forward_dependency_graph(project: Project, graph: DirectedGraph) -> str:
    """Format dependency graph for output."""
    content = []
    all_dependencies = ChainMap(*project.all_dependencies.values())
    top_level_dependencies = sorted(graph.iter_children(None), key=lambda p: p.name)
    for package in top_level_dependencies:
        if package.name in all_dependencies:
            required = specifier_from_requirement(all_dependencies[package.name])
        elif package_is_project(package, project):
            required = "This project"
        else:
            required = ""
        content.append(format_package(graph, package, required, ""))
    return "".join(content).strip()


def _format_reverse_dependency_graph(
    project: Project, graph: DirectedGraph[Package | None]
) -> str:
    """Format reverse dependency graph for output."""
    leaf_nodes = sorted(
        (node for node in graph if not list(graph.iter_children(node)) and node),
        key=lambda p: p.name,
    )
    content = [
        format_reverse_package(graph, node, prefix="") for node in leaf_nodes if node
    ]
    return "".join(content).strip()


def build_forward_dependency_json_subtree(
    root: Package,
    project: Project,
    graph: DirectedGraph[Package | None],
    required_by: Package = None,
    visited: frozenset[str] = frozenset(),
) -> dict:
    if not package_is_project(root, project):
        requirements = (
            required_by.requirements
            if required_by
            else ChainMap(*project.all_dependencies.values())
        )
        if root.name in requirements:
            required = specifier_from_requirement(requirements[root.name])
        else:
            required = "Not required"
    else:
        required = "This project"

    children = graph.iter_children(root) if root.name not in visited else []

    return OrderedDict(
        package=root.name,
        version=root.version,
        required=required,
        dependencies=sorted(
            (
                build_forward_dependency_json_subtree(
                    p, project, graph, root, visited | {root.name}
                )
                for p in children
                if p
            ),
            key=lambda d: d["package"],
        ),
    )


def build_reverse_dependency_json_subtree(
    root: Package,
    project: Project,
    graph: DirectedGraph[Package | None],
    requires: Package = None,
    visited: frozenset[str] = frozenset(),
) -> dict:
    parents = graph.iter_parents(root) if root.name not in visited else []
    return OrderedDict(
        package=root.name,
        version=root.version,
        requires=specifier_from_requirement(root.requirements[requires.name])
        if requires
        else None,
        dependents=sorted(
            (
                build_reverse_dependency_json_subtree(
                    p, project, graph, root, visited | {root.name}
                )
                for p in parents
                if p
            ),
            key=lambda d: d["package"],
        ),
    )


def build_dependency_json_tree(
    project: Project, graph: DirectedGraph[Package | None], reverse: bool
) -> list[dict]:
    if reverse:
        top_level_packages = filter(
            lambda n: not list(graph.iter_children(n)), graph
        )  # leaf nodes
        build_dependency_json_subtree: Callable = build_reverse_dependency_json_subtree
    else:
        top_level_packages = graph.iter_children(None)  # root nodes
        build_dependency_json_subtree = build_forward_dependency_json_subtree
    return [
        build_dependency_json_subtree(p, project, graph)
        for p in sorted(top_level_packages, key=lambda p: p.name if p else "")
        if p
    ]


def format_dependency_graph(
    project: Project,
    graph: DirectedGraph[Package | None],
    reverse: bool = False,
    json: bool = False,
) -> str:
    if json:
        return dumps(
            build_dependency_json_tree(project, graph, reverse),
            indent=2,
        )

    if reverse:
        return _format_reverse_dependency_graph(project, graph)
    else:
        return _format_forward_dependency_graph(project, graph)


def format_lockfile(
    project: Project,
    mapping: dict[str, Candidate],
    fetched_dependencies: dict[str, list[Requirement]],
) -> dict:
    """Format lock file from a dict of resolved candidates, a mapping of dependencies
    and a collection of package summaries.
    """
    packages = tomlkit.aot()
    file_hashes = tomlkit.table()
    for k, v in sorted(mapping.items()):
        base = tomlkit.table()
        base.update(v.as_lockfile_entry(project.root))  # type: ignore
        base.add("summary", v.summary or "")
        deps = make_array(sorted(r.as_line() for r in fetched_dependencies[k]), True)
        if len(deps) > 0:
            base.add("dependencies", deps)
        packages.append(base)  # type: ignore
        if v.hashes:
            key = f"{strip_extras(k)[0]} {v.version}"
            if key in file_hashes:
                continue
            array = tomlkit.array().multiline(True)
            for filename, hash_value in v.hashes.items():
                inline = make_inline_table({"file": filename, "hash": hash_value})
                array.append(inline)  # type: ignore
            if array:
                file_hashes.add(key, array)
    doc = tomlkit.document()
    doc.add("package", packages)  # type: ignore
    metadata = tomlkit.table()
    metadata.add("files", file_hashes)
    doc.add("metadata", metadata)  # type: ignore
    return cast(dict, doc)


def save_version_specifiers(
    requirements: dict[str, dict[str, Requirement]],
    resolved: dict[str, Candidate],
    save_strategy: str,
) -> None:
    """Rewrite the version specifiers according to the resolved result and save strategy

    :param requirements: the requirements to be updated
    :param resolved: the resolved mapping
    :param save_strategy: compatible/wildcard/exact
    """
    for reqs in requirements.values():
        for name, r in reqs.items():
            if r.is_named and not r.specifier:
                if save_strategy == "exact":
                    r.specifier = get_specifier(f"=={resolved[name].version}")
                elif save_strategy == "compatible":
                    version = str(resolved[name].version)
                    parsed = parse_version(version)
                    if parsed.is_prerelease or parsed.is_devrelease:
                        r.specifier = get_specifier(f">={version},<{parsed.major + 1}")
                    else:
                        r.specifier = get_specifier(f"~={parsed.major}.{parsed.minor}")
                elif save_strategy == "minimum":
                    r.specifier = get_specifier(f">={resolved[name].version}")


def check_project_file(project: Project) -> None:
    """Check the existence of the project file and throws an error on failure."""
    if not project.meta:
        raise ProjectError(
            "The pyproject.toml has not been initialized yet. You can do this "
            "by running {}.".format(termui.green("'pdm init'"))
        )


def find_importable_files(project: Project) -> Iterable[tuple[str, Path]]:
    """Find all possible files that can be imported"""
    for filename in (
        "Pipfile",
        "pyproject.toml",
        "requirements.in",
        "requirements.txt",
    ):
        project_file = project.root / filename
        if not project_file.exists():
            continue
        for key, module in FORMATS.items():
            if module.check_fingerprint(project, project_file.as_posix()):
                yield key, project_file


def set_env_in_reg(env_name: str, value: str) -> None:
    """Manipulate the WinReg, and add value to the
    environment variable if exists or create new.
    """
    import winreg

    value = os.path.normcase(value)

    with winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER) as root:
        with winreg.OpenKey(root, "Environment", 0, winreg.KEY_ALL_ACCESS) as env_key:
            try:
                old_value, type_ = winreg.QueryValueEx(env_key, env_name)
                paths = [os.path.normcase(item) for item in old_value.split(os.pathsep)]
                if value in paths:
                    return
            except FileNotFoundError:
                paths, type_ = [], winreg.REG_EXPAND_SZ
            new_value = os.pathsep.join([value] + paths)
            winreg.SetValueEx(env_key, env_name, 0, type_, new_value)


def format_resolution_impossible(err: ResolutionImpossible) -> str:
    from pdm.resolver.python import PythonRequirement

    causes: list[RequirementInformation] = err.causes
    info_lines: set[str] = set()
    if all(isinstance(cause.requirement, PythonRequirement) for cause in causes):
        project_requires = next(
            (cause.requirement for cause in causes if cause.parent is None)
        )
        conflicting = [
            cause
            for cause in causes
            if cause.parent is not None
            and not cause.requirement.specifier.is_superset(project_requires.specifier)
        ]
        result = [
            "Unable to find a resolution because the following dependencies don't work "
            "on all Python versions defined by the project's `requires-python`: "
            f"{termui.green(str(project_requires.specifier))}"
        ]
        for req, parent in conflicting:
            info_lines.add(f"  {req.as_line()} (from {repr(parent)})")
        result.extend(sorted(info_lines))
        result.append(
            "To fix this, you can change the value of `requires-python` "
            "in pyproject.toml."
        )
        return "\n".join(result)

    if len(causes) == 1:
        return (
            "Unable to find a resolution for "
            f"{termui.green(causes[0].requirement.identify())}\n"
            "Please make sure the package name is correct."
        )

    result = [
        f"Unable to find a resolution for "
        f"{termui.green(causes[0].requirement.identify())} because of the following "
        "conflicts:"
    ]
    for req, parent in causes:
        info_lines.add(
            f"  {req.as_line()} (from {repr(parent) if parent else 'project'})"
        )
    result.extend(sorted(info_lines))
    result.append(
        "To fix this, you could loosen the dependency version constraints in "
        "pyproject.toml. See https://pdm.fming.dev/usage/dependency"
        "/#solve-the-locking-failure for more details."
    )
    return "\n".join(result)


def translate_groups(
    project: Project, default: bool, dev: bool, groups: Iterable[str]
) -> list[str]:
    """Translate default, dev and groups containing ":all" into a list of groups"""
    optional_groups = set(project.meta.optional_dependencies or [])
    dev_groups = set(project.tool_settings.get("dev-dependencies", []))
    groups_set = set(groups)
    if dev is None:
        dev = True
    if groups_set & dev_groups:
        if not dev:
            raise PdmUsageError(
                "--prod is not allowed with dev groups and should be left"
            )
    elif dev:
        groups_set.update(dev_groups)
    if ":all" in groups:
        groups_set.discard(":all")
        groups_set.update(optional_groups)
    if default:
        groups_set.add("default")
    # Sorts the result in ascending order instead of in random order
    # to make this function pure
    invalid_groups = groups_set - set(project.iter_groups())
    if invalid_groups:
        project.core.ui.echo(
            f"Ignoring non-existing groups: {invalid_groups}", fg="yellow", err=True
        )
        groups_set -= invalid_groups
    return sorted(groups_set)


def merge_dictionary(
    target: MutableMapping[Any, Any], input: Mapping[Any, Any]
) -> None:
    """Merge the input dict with the target while preserving the existing values
    properly. This will update the target dictionary in place.
    """
    for key, value in input.items():
        if key not in target:
            target[key] = value
        elif isinstance(value, dict):
            target[key].update(value)
        elif isinstance(value, list):
            target[key].extend(value)
        else:
            target[key] = value


def is_pipx_installation() -> bool:
    return sys.prefix.split(os.sep)[-3:-1] == ["pipx", "venvs"]


def is_homebrew_installation() -> bool:
    return "/libexec" in sys.prefix.replace("\\", "/")


def is_scoop_installation() -> bool:
    return os.name == "nt" and is_path_relative_to(
        sys.prefix, Path.home() / "scoop/apps/pdm"
    )


def get_dist_location(dist: Distribution) -> str:
    direct_url = dist.read_text("direct_url.json")
    if not direct_url:
        return ""
    direct_url_data = json.loads(direct_url)
    url = cast(str, direct_url_data["url"])
    if url.startswith("file:"):
        path = url_to_path(url)
        editable = direct_url_data.get("dir_info", {}).get("editable", False)
        return f"{'-e ' if editable else ''}{path}"
    return ""
