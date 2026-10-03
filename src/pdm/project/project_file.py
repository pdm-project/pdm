from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any, Literal, TypedDict, Union, cast

import tomlkit

from pdm import termui
from pdm.exceptions import ProjectError
from pdm.project.toml_file import TOMLFile
from pdm.utils import normalize_name

if TYPE_CHECKING:
    from os import PathLike


def _remove_empty_tables(doc: dict) -> None:
    for k, v in list(doc.items()):
        if isinstance(v, dict):
            _remove_empty_tables(v)
            if not v:
                del doc[k]


class PyProject(TOMLFile):
    """The data object representing th pyproject.toml file"""

    def _parse(self) -> dict[str, Any]:
        data = super()._parse()
        self._convert_pyproject(data)
        return data

    def open_for_write(self) -> tomlkit.TOMLDocument:
        if self._for_write:
            return cast(tomlkit.TOMLDocument, self._data)
        doc = super().open_for_write()
        self._convert_pyproject(doc)
        return doc

    def _convert_pyproject(self, data: dict[str, Any]) -> None:
        from pdm.formats import flit, poetry

        if "project" not in data and self._path.exists():
            # Try converting from flit and poetry
            for converter in (flit, poetry):
                if converter.check_fingerprint(None, self._path):
                    metadata, settings = converter.convert(None, self._path, None)
                    data["project"] = metadata
                    if settings:
                        data.setdefault("tool", {}).setdefault("pdm", {}).update(settings)
                    break

    def write(self, show_message: bool = True) -> None:
        """Write the TOMLDocument to the file."""
        _remove_empty_tables(self._data.get("project", {}))
        if "tool" in self._data:
            tool_table = cast(dict, self._data["tool"])
            _remove_empty_tables(tool_table.get("pdm", {}))
            if "pdm" in tool_table and not tool_table["pdm"]:
                del tool_table["pdm"]
            if not tool_table:
                del self._data["tool"]

        if "dependency-groups" in self._data and not self.dependency_groups:
            del self._data["dependency-groups"]
        super().write()
        if show_message:
            self.ui.echo("Changes are written to [success]pyproject.toml[/].", verbosity=termui.Verbosity.NORMAL)

    @property
    def is_valid(self) -> bool:
        return bool(self._data.get("project"))

    @property
    def metadata(self) -> dict[str, Any]:
        return self._data.setdefault("project", {})

    @property
    def dependency_groups(self) -> dict[str, Any]:
        return self._data.setdefault("dependency-groups", {})

    @property
    def dev_dependencies(self) -> dict[str, list[Any]]:
        groups: dict[str, list[Any]] = {}
        for group, deps in self._data.get("dependency-groups", {}).items():
            group = normalize_name(group)
            if group in groups:
                raise ProjectError(f"The group {group} is duplicated in dependency-groups")
            groups[group] = deps.unwrap() if hasattr(deps, "unwrap") else deps
        for group, deps in self.settings.get("dev-dependencies", {}).items():
            group = normalize_name(group)
            groups.setdefault(group, []).extend(deps.unwrap() if hasattr(deps, "unwrap") else deps)
        return groups

    @property
    def settings(self) -> ToolPDMTable:
        return self._data.setdefault("tool", {}).setdefault("pdm", {})

    @property
    def build_system(self) -> dict[str, Any]:
        return self._data.get("build-system", {})

    @property
    def resolution(self) -> ResolutionTable:
        """A compatible getter method for the resolution overrides
        in the pyproject.toml file.
        """
        return self.settings.get("resolution", {})

    @property
    def allow_prereleases(self) -> bool | None:
        return self.resolution.get("allow-prereleases")

    def content_hash(self, algo: str = "sha256") -> str:
        """Generate a hash of the sensible content of the pyproject.toml file.
        When the hash changes, it means the project needs to be relocked.
        """
        dump_data = {
            "sources": self.settings.get("source", []),
            "dependencies": self.metadata.get("dependencies", []),
            "dev-dependencies": self.dev_dependencies,
            "optional-dependencies": self.metadata.get("optional-dependencies", {}),
            "requires-python": self.metadata.get("requires-python", ""),
            "resolution": self.resolution,
        }
        pyproject_content = json.dumps(dump_data, sort_keys=True)
        hasher = hashlib.new(algo)
        hasher.update(pyproject_content.encode("utf-8"))
        return hasher.hexdigest()

    @property
    def plugins(self) -> list[str]:
        return self.settings.get("plugins", [])


BuildTable = TypedDict(
    "BuildTable",
    {
        "custom-hook": str,
        "editable-backend": Literal["editables", "path"],
        "excludes": list[str],
        "includes": list[str],
        "is-purelib": bool,
        "package-dir": str,
        "run-setuptools": bool,
        "source-includes": list[str],
        "wheel-data": dict[
            Literal["data", "include", "platinclude", "platlib", "purelib", "scripts"],
            dict[Literal["path", "relative-to"], str],
        ],
    },
)
"""
`[tool.pdm.build]`

References:
    <https://backend.pdm-project.org/build_config/>
"""


class OptionsTable(TypedDict, total=False):
    """
    `[tool.pdm.options]`

    References:
        [Passing constant arguments to every pdm invocation][passing-constant-arguments-to-every-pdm-invocation]
    """

    add: list[str]
    build: list[str]
    cache: list[str]
    completion: list[str]
    config: list[str]
    export: list[str]
    fix: list[str]
    info: list[str]
    init: list[str]
    install: list[str]
    list: list[str]
    lock: list[str]
    new: list[str]
    outdated: list[str]
    publish: list[str]
    python: list[str]
    remove: list[str]
    run: list[str]
    search: list[str]
    self: list[str]
    show: list[str]
    sync: list[str]
    update: list[str]
    use: list[str]
    venv: list[str]


ResolutionTable = TypedDict(
    "ResolutionTable",
    {
        "allow-prereleases": bool,
        "exclude-newer": str,
        "excludes": list[str],
        "no-binary": Union[str, list[str]],
        "only-binary": Union[str, list[str]],
        "overrides": dict[str, str],
        "prefer-binary": Union[str, list[str]],
    },
    total=False,
)


class SourceTable(TypedDict, total=False):
    """
    A repository where PDM can find packages during lockfile resolution

    References:
        [Configure the package indexes][configure-the-package-indexes]
    """

    name: str
    url: str
    verify_ssl: bool
    username: str
    password: str
    type: Literal["index", "find_links"]
    include_packages: list[str]
    exclude_packages: list[str]


class VersionTable(TypedDict, total=False):
    """
    Specify how PDM computes dynamic versions.

    References:
        [Dynamic project version](https://backend.pdm-project.org/metadata/#dynamic-project-version)
    """

    source: Literal["call", "file", "scm"]
    getter: str
    path: PathLike[str]
    pattern: str
    fallback_version: str
    tag_filter: str
    tag_regex: str
    version_format: str
    write_to: str
    write_template: str


class UserScript(TypedDict, total=False):
    """
    The value of an item within `[tool.pdm.scripts]` .

    An individual script may be a simple string, or a dictionary of this form.

    Examples:

        [tool.pdm.scripts]
        list-files = "ls ."
        start = {cmd = "flask run -p 54321"}
        mytask.composite = [
            "echo 'Hello'",
            "echo 'World'"
        ]
        mytask.keep_going = true

    References:
        [PDM Scripts][pdm-scripts]
    """

    call: str
    composite: list[str]
    cmd: str
    env: dict[str, str]
    env_file: str | dict[Literal["override"], str]
    keep_going: bool
    shell: str
    working_dir: str


ToolPDMTable = TypedDict(
    "ToolPDMTable",
    {
        "distribution": bool,
        "ignore_package_warnings": list[str],
        "plugins": list[str],
        "build": BuildTable,
        # Control how pdm-backend builds the package
        "options": OptionsTable,
        # Add parameters to every pdm cli call
        "resolution": ResolutionTable,
        # Rules governing lockfile resolution
        "scripts": dict[str, Union[str, UserScript]],
        # See [pdm-scripts][pdm-scripts]
        "source": list[SourceTable],
        # Repositories where packages may be found
        "version": VersionTable,
        # Dynamic Versioning
        "dev-dependencies": dict[str, list[str]],
        # Development-only dependencies
    },
    total=False,
)
"""
Root table for setting pdm options within pyproject.toml
"""
