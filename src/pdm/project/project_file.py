from __future__ import annotations

import hashlib
import json
from typing import Mapping

from tomlkit import TOMLDocument, items

from pdm.project.toml_file import TOMLBase
from pdm.utils import deprecation_warning


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
        super().write()
        if show_message:
            self.ui.echo("Changes are written to [success]pyproject.toml[/].")

    @property
    def is_valid(self) -> bool:
        return "project" in self._data

    @property
    def metadata(self) -> items.Table:
        return self._data.setdefault("project", {})

    @property
    def settings(self) -> items.Table:
        return self._data.setdefault("tool", {}).setdefault("pdm", {})

    @property
    def build_system(self) -> dict:
        return self._data.get("build-system", {})

    @property
    def resolution_overrides(self) -> Mapping[str, str]:
        """A compatible getter method for the resolution overrides
        in the pyproject.toml file.
        """
        settings = self.settings
        if "overrides" in settings:
            deprecation_warning(
                "The 'tool.pdm.overrides' table has been renamed to "
                "'tool.pdm.resolution.overrides', please update the "
                "setting accordingly."
            )
            return settings["overrides"]
        return settings.get("resolution", {}).get("overrides", {})

    def content_hash(self, algo: str = "sha256") -> str:
        """Generate a hash of the sensible content of the pyproject.toml file.
        When the hash changes, it means the project needs to be relocked.
        """
        dump_data = {
            "sources": self.settings.get("source", []),
            "dependencies": self.metadata.get("dependencies", []),
            "dev-dependencies": self.settings.get("dev-dependencies", {}),
            "optional-dependencies": self.metadata.get("optional-dependencies", {}),
            "requires-python": self.metadata.get("requires-python", ""),
            "overrides": self.resolution_overrides,
        }
        pyproject_content = json.dumps(dump_data, sort_keys=True)
        hasher = hashlib.new(algo)
        hasher.update(pyproject_content.encode("utf-8"))
        return hasher.hexdigest()
