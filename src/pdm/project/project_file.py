from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, cast

from tomlkit import TOMLDocument, items

from pdm import termui
from pdm.exceptions import ProjectError
from pdm.project.toml_file import TOMLBase
from pdm.utils import normalize_name


def _remove_empty_tables(doc: dict) -> None:
    for k, v in list(doc.items()):
        if isinstance(v, dict):
            _remove_empty_tables(v)
            if not v:
                del doc[k]


class PyProject(TOMLBase):
    """The data object representing th pyproject.toml file"""

    def read(self) -> TOMLDocument:
        from pdm.formats import flit, poetry

        data = super().read()
        if "project" not in data and self._path.exists():
            # Try converting from flit and poetry
            for converter in (flit, poetry):
                if converter.check_fingerprint(None, self._path):
                    metadata, settings = converter.convert(None, self._path, None)
                    data["project"] = metadata
                    if settings:
                        data.setdefault("tool", {}).setdefault("pdm", {}).update(settings)
                    break
        return data

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
    def metadata(self) -> items.Table:
        return self._data.setdefault("project", {})

    @property
    def dependency_groups(self) -> items.Table:
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
    def settings(self) -> items.Table:
        return self._data.setdefault("tool", {}).setdefault("pdm", {})

    @property
    def build_system(self) -> dict:
        return self._data.get("build-system", {})

    @property
    def resolution(self) -> Mapping[str, Any]:
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
