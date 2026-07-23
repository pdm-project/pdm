from __future__ import annotations

import argparse
import contextlib
import io
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from argcomplete.completers import DirectoriesCompleter, FilesCompleter
from packaging.requirements import InvalidRequirement, Requirement

from pdm.compat import tomllib

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

    from pdm.core import Core


_FILE_DESTS = {
    "ca_certs",
    "config",
    "dest",
    "filename",
    "lockfile",
    "output",
    "override",
    "path",
    "project_path",
    "python",
}
_DIRECTORY_DESTS = {"dest", "project_path"}
_GROUP_DESTS = {"exclude", "excluded_groups", "group", "groups", "include"}
_PACKAGE_PATHS = {
    ("list",),
    ("remove",),
    ("show",),
    ("update",),
}
_SHELLS = ("bash", "zsh", "fish", "powershell", "pwsh")


def _project_root(parsed_args: argparse.Namespace) -> Path:
    if project_path := getattr(parsed_args, "project_path", None):
        return Path(project_path).expanduser().resolve()
    current = Path.cwd()
    for directory in (current, *current.parents):
        if directory.joinpath("pyproject.toml").is_file():
            return directory
    return current


def _load_pyproject(parsed_args: argparse.Namespace) -> dict[str, object]:
    pyproject = _project_root(parsed_args) / "pyproject.toml"
    if not pyproject.is_file():
        return {}
    try:
        with pyproject.open("rb") as file:
            return tomllib.load(file)
    except (OSError, ValueError):
        return {}


def _groups(prefix: str, parsed_args: argparse.Namespace, **_: Any) -> Mapping[str, str]:
    data = _load_pyproject(parsed_args)
    project = data.get("project", {})
    tool = data.get("tool", {})
    pdm = tool.get("pdm", {}) if isinstance(tool, dict) else {}
    names = {"default"}
    if isinstance(project, dict):
        optional = project.get("optional-dependencies", {})
        if isinstance(optional, dict):
            names.update(map(str, optional))
    dependency_groups = data.get("dependency-groups", {})
    if isinstance(dependency_groups, dict):
        names.update(map(str, dependency_groups))
    if isinstance(pdm, dict):
        dev = pdm.get("dev-dependencies", {})
        if isinstance(dev, dict):
            names.update(map(str, dev))

    completed, separator, _partial = prefix.rpartition(",")
    value_prefix = f"{completed}{separator}" if separator else ""
    return {f"{value_prefix}{name}": "Dependency group" for name in sorted(names)}


def _requirement_name(requirement: object) -> str | None:
    if not isinstance(requirement, str):
        return None
    try:
        return Requirement(requirement).name
    except InvalidRequirement:
        match = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", requirement)
        return match.group() if match else None


def _project_packages(parsed_args: argparse.Namespace) -> Mapping[str, str]:
    data = _load_pyproject(parsed_args)
    requirements: list[object] = []
    project = data.get("project", {})
    tool = data.get("tool", {})
    pdm = tool.get("pdm", {}) if isinstance(tool, dict) else {}
    if isinstance(project, dict):
        requirements.extend(project.get("dependencies", []) or [])
        optional = project.get("optional-dependencies", {})
        if isinstance(optional, dict):
            for values in optional.values():
                if isinstance(values, list):
                    requirements.extend(values)
    dependency_groups = data.get("dependency-groups", {})
    if isinstance(dependency_groups, dict):
        for values in dependency_groups.values():
            if isinstance(values, list):
                requirements.extend(values)
    if isinstance(pdm, dict):
        dev = pdm.get("dev-dependencies", {})
        if isinstance(dev, dict):
            for values in dev.values():
                if isinstance(values, list):
                    requirements.extend(values)
    names = {name for item in requirements if (name := _requirement_name(item))}
    return dict.fromkeys(sorted(names, key=str.lower), "Project dependency")


def _packages(parsed_args: argparse.Namespace, **_: Any) -> Mapping[str, str]:
    return _project_packages(parsed_args)


def _scripts(parsed_args: argparse.Namespace, **_: Any) -> Mapping[str, str]:
    data = _load_pyproject(parsed_args)
    tool = data.get("tool", {})
    pdm = tool.get("pdm", {}) if isinstance(tool, dict) else {}
    scripts = pdm.get("scripts", {}) if isinstance(pdm, dict) else {}
    if not isinstance(scripts, dict):
        return {}
    return {str(name): "Project script" for name in sorted(scripts)}


def _config_keys(**_: Any) -> Mapping[str, str]:
    from pdm.project.config import Config

    return {name: item.description for name, item in sorted(Config._config_map.items()) if item.should_show()}


def _venvs(core: Core, parsed_args: argparse.Namespace, **_: Any) -> Mapping[str, str]:
    from pdm.cli.commands.venv.utils import iter_venvs

    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            project = core.create_project(_project_root(parsed_args))
            return {name: str(venv.root) for name, venv in iter_venvs(project)}
    except Exception:
        return {}


def _shells(**_: Any) -> Iterable[str]:
    return _SHELLS


def _set_completer(action: argparse.Action, completer: Callable[..., object]) -> None:
    action.completer = completer  # type: ignore[attr-defined]


def configure_parser(core: Core) -> None:
    """Attach value completers to PDM's fully constructed argument parser."""
    files_completer = FilesCompleter()
    directories_completer = DirectoriesCompleter()

    def visit(parser: argparse.ArgumentParser, path: tuple[str, ...] = ()) -> None:
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                if not path:
                    _set_completer(action, _scripts)
                for name, subparser in action.choices.items():
                    visit(subparser, (*path, name))
            elif action.dest in _GROUP_DESTS:
                _set_completer(action, _groups)
            elif action.dest in {"use_venv", "env", "venv"}:
                _set_completer(action, lambda **kwargs: _venvs(core, **kwargs))
            elif action.dest == "key" and path == ("config",):
                _set_completer(action, _config_keys)
            elif action.dest == "script" and path == ("run",):
                _set_completer(action, _scripts)
            elif action.dest in {"package", "packages", "patterns"} and path in _PACKAGE_PATHS:
                _set_completer(action, _packages)
            elif action.dest == "shell" and path == ("completion",):
                _set_completer(action, _shells)
            elif action.dest in _FILE_DESTS:
                completer = directories_completer if action.dest in _DIRECTORY_DESTS else files_completer
                _set_completer(action, completer)

    visit(core.parser)


__all__ = ["configure_parser"]
