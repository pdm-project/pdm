from __future__ import annotations

import argparse
import dataclasses as dc
import json
import os
import re
import sys
from collections import OrderedDict
from fnmatch import fnmatch
from gettext import gettext as _
from json import dumps
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Iterable,
    Mapping,
    MutableMapping,
    cast,
    no_type_check,
)

from packaging.specifiers import SpecifierSet
from resolvelib.structs import DirectedGraph
from rich.tree import Tree

from pdm import termui
from pdm.exceptions import PdmArgumentError, ProjectError
from pdm.models.markers import EnvSpec
from pdm.models.requirements import (
    Requirement,
    filter_requirements_with_extras,
    strip_extras,
)
from pdm.models.specifiers import PySpecSet, get_specifier
from pdm.utils import (
    comparable_version,
    is_path_relative_to,
    normalize_name,
    url_to_path,
)

if TYPE_CHECKING:
    from argparse import Action, _ArgumentGroup

    from packaging.version import Version
    from resolvelib.resolvers import RequirementInformation, ResolutionImpossible

    from pdm.compat import Distribution
    from pdm.compat import importlib_metadata as im
    from pdm.models.candidates import Candidate
    from pdm.project import Project


class PdmFormatter(argparse.RawDescriptionHelpFormatter):
    def start_section(self, heading: str | None) -> None:
        return super().start_section(termui.style(heading.title() if heading else "", style="warning"))

    def _format_usage(
        self,
        usage: str | None,
        actions: Iterable[Action],
        groups: Iterable[_ArgumentGroup],
        prefix: str | None,
    ) -> str:
        if prefix is None:
            prefix = "Usage: "
        result = super()._format_usage(usage, actions, groups, prefix)  # type: ignore[arg-type]
        # Remove continuous spaces
        result = re.sub(r" +", " ", result)
        if prefix:
            return result.replace(prefix, termui.style(prefix, style="warning"))
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
            tup = self._current_indent, "", action_width, action_header  # type: ignore[assignment]
            action_header = "%*s%-*s  " % tup  # type: ignore[str-format]
            indent_first = 0

        # long action name; start on the next line
        else:
            tup = self._current_indent, "", action_header
            action_header = "%*s%s\n" % tup
            indent_first = help_position

        # Special format for empty action_header
        # - No extra indent block
        # - Help info in the same indent level as subactions
        if not action_header.strip():
            action_header = ""
            help_position = self._current_indent
            indent_first = self._current_indent

        # collect the pieces of the action help
        parts = [termui.style(action_header, style="primary")]

        # if there was help for the action, add lines of help text
        if action.help:
            help_text = self._expand_help(action)
            help_lines = self._split_lines(help_text, help_width)
            parts.append("%*s%s\n" % (indent_first, "", help_lines[0]))
            for line in help_lines[1:]:
                parts.append("%*s%s\n" % (help_position, "", line))

        # or add a newline if the description doesn't end with one
        elif not action_header.endswith("\n"):
            if action_header:
                parts.append("\n")

        # cancel out extra indent when action_header is empty
        if not action_header:
            self._dedent()
        # if there are any sub-actions, add their help as well
        for subaction in self._iter_indented_subactions(action):
            parts.append(self._format_action(subaction))
        # cancel out extra dedent when action_header is empty
        if not action_header:
            self._indent()

        # return a single string
        return self._join_parts(parts)


class ArgumentParser(argparse.ArgumentParser):
    """A standard argument parser but with title-cased help."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs["formatter_class"] = PdmFormatter
        kwargs["add_help"] = False
        super().__init__(*args, **kwargs)
        self.add_argument(
            "-h", "--help", action="help", default=argparse.SUPPRESS, help="Show this help message and exit."
        )
        self._optionals.title = "options"

    def parse_known_args(self, args: Any = None, namespace: Any = None) -> Any:
        args, argv = super().parse_known_args(args, namespace)
        if argv:
            msg = _("unrecognized arguments: %s")
            self.error(msg % " ".join(argv))
        return args, argv


class ErrorArgumentParser(ArgumentParser):
    """A subclass of argparse.ArgumentParser that raises
    parsing error rather than exiting.

    This does the same as passing exit_on_error=False on Python 3.9+
    """

    def _parse_known_args(
        self, arg_strings: list[str], namespace: argparse.Namespace
    ) -> tuple[argparse.Namespace, list[str]]:
        try:
            return super()._parse_known_args(arg_strings, namespace)
        except argparse.ArgumentError as e:
            # We raise a dedicated error to avoid being caught by the caller
            raise PdmArgumentError(e) from e


@dc.dataclass(frozen=True)
class PackageNode:
    """An internal class for the convenience of dependency graph building."""

    name: str = dc.field(hash=True, compare=True)
    version: str | None = dc.field(compare=False)
    requirements: dict[str, Requirement] = dc.field(compare=False)

    def __repr__(self) -> str:
        return f"<Package {self.name}=={self.version}>"


def build_dependency_graph(
    working_set: Mapping[str, im.Distribution],
    env_spec: EnvSpec,
    selected: set[str] | None = None,
    include_sub: bool = True,
) -> DirectedGraph:
    """Build a dependency graph from locked result."""
    graph: DirectedGraph[PackageNode | None] = DirectedGraph()
    graph.add(None)  # sentinel parent of top nodes.
    node_with_extras: set[str] = set()

    def add_package(key: str, dist: Distribution | None) -> PackageNode:
        name, extras = strip_extras(key)
        extras = extras or ()
        reqs: dict[str, Requirement] = {}
        if dist:
            requirements = filter_requirements_with_extras(dist.requires or [], extras, include_default=True)
            for req in requirements:
                if not req.marker or req.marker.matches(env_spec):
                    reqs[req.identify()] = req
            version: str | None = dist.version
        else:
            version = None

        node = PackageNode(key, version, reqs)
        if node not in graph:
            if extras:
                node_with_extras.add(name)
            graph.add(node)
            if include_sub:
                for k in reqs:
                    child = add_package(k, working_set.get(strip_extras(k)[0]))
                    graph.connect(node, child)

        return node

    selected_map: dict[str, str] = {}
    for key in selected or ():
        name = key.split("[")[0]
        if len(key) >= len(selected_map.get(name, "")):
            # Ensure key with extras remains
            selected_map[name] = key
    for k, dist in working_set.items():
        if selected is not None:
            name = k.split("[")[0]
            if name not in selected_map:
                continue
            k = selected_map[name]
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


def specifier_from_requirement(requirement: Requirement) -> str:
    return str(requirement.specifier) or "Any"


def add_package_to_tree(
    root: Tree,
    graph: DirectedGraph,
    package: PackageNode,
    required: list[str],
    visited: frozenset[str] = frozenset(),
) -> None:
    """Format one package.

    :param graph: the dependency graph
    :param package: the package instance
    :param required: the version required by its parent
    :param visited: the visited package collection
    """
    version = (
        "[error][ not installed ][/]"
        if not package.version
        else f"[error]{package.version}[/]"
        if required
        and not any(s in ("Any", "This project") or SpecifierSet(s).contains(package.version) for s in required)
        else f"[warning]{package.version}[/]"
    )
    # escape deps with extras
    name = package.name.replace("[", r"\[") if "[" in package.name else package.name
    if package.name in visited:
        version = r"[error]\[circular][/]"
    req_str = f"[ required: {'&&'.join(required)} ]" if required else "[ Not required ]"
    node = root.add(f"[req]{name}[/] {version} {req_str}")
    if package.name in visited:
        return
    children = sorted(graph.iter_children(package), key=lambda p: p.name)
    for child in children:
        required = [specifier_from_requirement(package.requirements[child.name])]
        add_package_to_tree(node, graph, child, required, visited | {package.name})


def add_package_to_reverse_tree(
    root: Tree,
    graph: DirectedGraph,
    package: PackageNode,
    child: PackageNode | None = None,
    requires: str = "",
    visited: frozenset[str] = frozenset(),
) -> None:
    """Format one package for output reverse dependency graph."""
    version = "[error][ not installed ][/]" if not package.version else f"[warning]{package.version}[/]"
    if package.name in visited:
        version = r"[error]\[circular][/]"
    requires = (
        f"[ requires: [error]{requires}[/] ]"
        if requires not in ("Any", "")
        and child
        and child.version
        and not SpecifierSet(requires).contains(child.version)
        else ""
        if not requires
        else f"[ requires: {requires} ]"
    )
    name = package.name.replace("[", r"\[") if "[" in package.name else package.name
    node = root.add(f"[req]{name}[/] {version} {requires}")

    if package.name in visited:
        return
    parents: list[PackageNode] = sorted(filter(None, graph.iter_parents(package)), key=lambda p: p.name)
    for parent in parents:
        requires = specifier_from_requirement(parent.requirements[package.name])
        add_package_to_reverse_tree(node, graph, parent, package, requires, visited=visited | {package.name})
    return


def package_is_project(package: PackageNode, project: Project) -> bool:
    return project.is_distribution and package.name == normalize_name(project.name)


def _format_forward_dependency_graph(
    project: Project, graph: DirectedGraph[PackageNode | None], patterns: list[str]
) -> Tree:
    """Format dependency graph for output."""
    root = Tree("Dependencies", hide_root=True)

    def find_package_to_add(package: PackageNode) -> PackageNode | None:
        if not patterns:
            return package
        to_check = [package]
        while to_check:
            package = to_check.pop(0)
            if package and package_match_patterns(package, patterns):
                return package
            to_check.extend(graph.iter_children(package))
        return None

    all_dependencies = {
        r.identify(): r
        for deps in project.all_dependencies.values()
        for r in deps
        if not r.marker or r.marker.matches(project.environment.spec)
    }
    top_level_dependencies = {find_package_to_add(node) for node in graph.iter_children(None) if node}
    for package in sorted((node for node in top_level_dependencies if node), key=lambda p: p.name):
        required: set[str] = set()
        for parent in graph.iter_parents(package):
            if parent:
                r = specifier_from_requirement(parent.requirements[package.name])
            elif package.name in all_dependencies:
                r = specifier_from_requirement(all_dependencies[package.name])
            elif package_is_project(package, project):
                r = "This project"
            else:
                continue
            required.add(r)
        add_package_to_tree(root, graph, package, sorted(required))
    return root


def _format_reverse_dependency_graph(
    project: Project, graph: DirectedGraph[PackageNode | None], patterns: list[str]
) -> Tree:
    """Format reverse dependency graph for output."""

    def find_package_to_add(package: PackageNode) -> PackageNode | None:
        if not patterns:
            return package
        to_check = [package]
        while to_check:
            package = to_check.pop(0)
            if package and package_match_patterns(package, patterns):
                return package
            to_check.extend(graph.iter_parents(package))
        return None

    root = Tree("Dependencies", hide_root=True)
    leaf_nodes = {find_package_to_add(node) for node in graph if not list(graph.iter_children(node)) and node}
    for package in sorted((node for node in leaf_nodes if node), key=lambda p: p.name):
        if not package:
            continue
        add_package_to_reverse_tree(root, graph, package)
    return root


def build_forward_dependency_json_subtree(
    root: PackageNode,
    project: Project,
    graph: DirectedGraph[PackageNode | None],
    required_by: PackageNode | None = None,
    visited: frozenset[str] = frozenset(),
) -> dict:
    required: set[str] = set()
    all_dependencies = {
        r.identify(): r
        for deps in project.all_dependencies.values()
        for r in deps
        if not r.marker or r.marker.matches(project.environment.spec)
    }
    for parent in graph.iter_parents(root):
        if parent:
            r = specifier_from_requirement(parent.requirements[root.name])
        elif not package_is_project(root, project):
            requirements = required_by.requirements if required_by else all_dependencies
            if root.name in requirements:
                r = specifier_from_requirement(requirements[root.name])
            else:
                continue
        else:
            r = "This project"
        required.add(r)

    children = graph.iter_children(root) if root.name not in visited else []

    return OrderedDict(
        package=root.name,
        version=root.version,
        required="&&".join(sorted(required)),
        dependencies=sorted(
            (
                build_forward_dependency_json_subtree(p, project, graph, root, visited | {root.name})
                for p in children
                if p
            ),
            key=lambda d: d["package"],
        ),
    )


def build_reverse_dependency_json_subtree(
    root: PackageNode,
    project: Project,
    graph: DirectedGraph[PackageNode | None],
    requires: PackageNode | None = None,
    visited: frozenset[str] = frozenset(),
) -> dict:
    parents = graph.iter_parents(root) if root.name not in visited else []
    return OrderedDict(
        package=root.name,
        version=root.version,
        requires=specifier_from_requirement(root.requirements[requires.name]) if requires else None,
        dependents=sorted(
            (
                build_reverse_dependency_json_subtree(p, project, graph, root, visited | {root.name})
                for p in parents
                if p
            ),
            key=lambda d: d["package"],
        ),
    )


def package_match_patterns(package: PackageNode, patterns: list[str]) -> bool:
    return not patterns or any(fnmatch(package.name, pattern) for pattern in patterns)


def build_dependency_json_tree(
    project: Project, graph: DirectedGraph[PackageNode | None], reverse: bool, patterns: list[str]
) -> list[dict]:
    def find_package_to_add(package: PackageNode) -> PackageNode | None:
        if not patterns:
            return package
        to_check = [package]
        while to_check:
            package = to_check.pop(0)
            if package and package_match_patterns(package, patterns):
                return package
            if reverse:
                to_check.extend(graph.iter_parents(package))
            else:
                to_check.extend(graph.iter_children(package))
        return None

    top_level_packages: Iterable[PackageNode | None]
    if reverse:
        top_level_packages = filter(lambda n: not list(graph.iter_children(n)), graph)  # leaf nodes
        build_dependency_json_subtree: Callable = build_reverse_dependency_json_subtree
    else:
        top_level_packages = graph.iter_children(None)  # root nodes
        build_dependency_json_subtree = build_forward_dependency_json_subtree
    top_level_packages = {find_package_to_add(node) for node in top_level_packages if node}
    return [
        build_dependency_json_subtree(p, project, graph)
        for p in sorted((node for node in top_level_packages if node), key=lambda p: p.name)
    ]


def show_dependency_graph(
    project: Project,
    graph: DirectedGraph[PackageNode | None],
    reverse: bool = False,
    json: bool = False,
    patterns: list[str] | None = None,
) -> None:
    echo = project.core.ui.echo
    if patterns is None:
        patterns = []
    if json:
        echo(
            dumps(
                build_dependency_json_tree(project, graph, reverse, patterns),
                indent=2,
            )
        )
        return

    if reverse:
        tree = _format_reverse_dependency_graph(project, graph, patterns)
    else:
        tree = _format_forward_dependency_graph(project, graph, patterns)
    echo(tree)


def save_version_specifiers(
    requirements: Iterable[Requirement],
    resolved: dict[str, list[Candidate]],
    save_strategy: str,
) -> None:
    """Rewrite the version specifiers according to the resolved result and save strategy

    :param requirements: the requirements to be updated
    :param resolved: the resolved mapping
    :param save_strategy: compatible/wildcard/exact
    """

    def candidate_version(candidates: list[Candidate]) -> Version | None:
        if len(candidates) > 1:
            return None
        c = candidates[0]
        assert c.version is not None
        return comparable_version(c.version)

    for r in requirements:
        name = r.identify()
        if r.is_named and not r.specifier and name in resolved:
            version = candidate_version(resolved[name])
            if version is None:
                continue
            if save_strategy == "exact":
                r.specifier = get_specifier(f"=={version}")
            elif save_strategy == "compatible":
                if version.is_prerelease or version.is_devrelease:
                    r.specifier = get_specifier(f">={version},<{version.major + 1}")
                else:
                    r.specifier = get_specifier(f"~={version.major}.{version.minor}")
            elif save_strategy == "minimum":
                r.specifier = get_specifier(f">={version}")


def check_project_file(project: Project) -> None:
    """Check the existence of the project file and throws an error on failure."""
    if not project.pyproject.is_valid:
        raise ProjectError(
            "The pyproject.toml has not been initialized yet. You can do this by running [success]`pdm init`[/]."
        ) from None


def find_importable_files(project: Project) -> Iterable[tuple[str, Path]]:
    """Find all possible files that can be imported"""
    from pdm.formats import FORMATS

    for filename in ("Pipfile", "pyproject.toml", "requirements.in", "requirements.txt", "setup.py", "setup.cfg"):
        project_file = project.root / filename
        if not project_file.exists():
            continue
        for key, module in FORMATS.items():
            if module.check_fingerprint(project, project_file.as_posix()):
                yield key, project_file


@no_type_check
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
            new_value = os.pathsep.join([value, *paths])
            winreg.SetValueEx(env_key, env_name, 0, type_, new_value)


def format_resolution_impossible(err: ResolutionImpossible) -> str:
    from pdm.resolver.python import PythonRequirement

    causes: list[RequirementInformation] = err.causes
    info_lines: set[str] = set()
    if not causes:
        return ""
    if all(isinstance(cause.requirement, PythonRequirement) for cause in causes):
        project_requires: PythonRequirement = next(cause.requirement for cause in causes if cause.parent is None)
        pyspec = cast(PySpecSet, project_requires.specifier)
        conflicting = [
            cause
            for cause in causes
            if cause.parent is not None and not cause.requirement.specifier.is_superset(pyspec)
        ]
        result = [
            "Unable to find a resolution because the following dependencies don't work "
            "on all Python versions in the range of the project's `requires-python`: "
            f"[success]{pyspec}[/]."
        ]
        for req, parent in conflicting:
            pyspec &= req.specifier
            info_lines.add(f"  {req.as_line()} (from {parent!r})")
        result.extend(sorted(info_lines))
        if pyspec.is_empty():
            result.append("Consider changing the version specifiers of the dependencies to be compatible")
        else:
            result.append(
                "A possible solution is to change the value of `requires-python` "
                f"in pyproject.toml to [success]{pyspec}[/]."
            )
        return "\n".join(result)

    if len(causes) == 1:
        return (
            "Unable to find a resolution for "
            f"[success]{causes[0].requirement.identify()}[/]\n"
            "Please make sure the package name is correct."
        )

    result = [
        "Unable to find a resolution for "
        f"[success]{causes[0].requirement.identify()}[/]\n"
        "because of the following conflicts:"
    ]
    for req, parent in causes:
        info_lines.add(f"  {req.as_line()} (from {parent if parent else 'project'})")
    result.extend(sorted(info_lines))
    result.append(
        "To fix this, you could loosen the dependency version constraints in "
        "pyproject.toml. See https://pdm-project.org/en/latest/usage/lockfile/"
        "#solve-the-locking-failure for more details."
    )
    return "\n".join(result)


def merge_dictionary(target: MutableMapping[Any, Any], input: Mapping[Any, Any], append_array: bool = True) -> None:
    """Merge the input dict with the target while preserving the existing values
    properly. This will update the target dictionary in place.
    List values will be extended, but only if the value is not already in the list.
    """
    for key, value in input.items():
        if key not in target:
            target[key] = value
        elif isinstance(target[key], dict):
            merge_dictionary(target[key], value, append_array=append_array)
        elif isinstance(target[key], list) and append_array:
            target[key].extend(x for x in value if x not in target[key])
            if hasattr(target[key], "multiline"):
                target[key].multiline(True)  # type: ignore[attr-defined]
        else:
            target[key] = value


def is_pipx_installation() -> bool:
    return sys.prefix.split(os.sep)[-3:-1] == ["pipx", "venvs"]


def is_homebrew_installation() -> bool:
    return "/libexec" in sys.prefix.replace("\\", "/")


def is_scoop_installation() -> bool:
    return os.name == "nt" and is_path_relative_to(sys.prefix, Path.home() / "scoop/apps/pdm")


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


def get_pep582_path(project: Project) -> str:
    from pdm.compat import resources_open_binary

    script_dir = Path(__file__).parent.parent / "pep582"
    if script_dir.exists():
        return str(script_dir)

    script_dir = project.global_config.config_file.parent / "pep582"
    if script_dir.joinpath("sitecustomize.py").exists():
        return str(script_dir)
    script_dir.mkdir(parents=True, exist_ok=True)
    with resources_open_binary("pdm.pep582", "sitecustomize.py") as f:
        script_dir.joinpath("sitecustomize.py").write_bytes(f.read())
    return str(script_dir)


def use_venv(project: Project, name: str) -> None:
    from pdm.cli.commands.venv.utils import get_venv_with_name
    from pdm.environments import PythonEnvironment

    venv = get_venv_with_name(project, cast(str, name))
    project.core.ui.info(f"In virtual environment: [success]{venv.root}[/]", verbosity=termui.Verbosity.DETAIL)
    project.environment = PythonEnvironment(project, python=str(venv.interpreter))


def normalize_pattern(pattern: str) -> str:
    """Normalize a pattern to a valid name for a package."""
    return re.sub(r"[^A-Za-z0-9*?]+", "-", pattern).lower()
