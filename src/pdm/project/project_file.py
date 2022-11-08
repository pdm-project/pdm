from __future__ import annotations

import hashlib
import json

from tomlkit import TOMLDocument, items

from pdm.exceptions import ProjectError
from pdm.project.toml_file import TOMLBase


class PyProject(TOMLBase):
    """The data object representing th pyproject.toml file"""

    def read(self) -> TOMLDocument:
        from pdm.formats import flit, poetry

        data = super().read()
        if "project" not in data:
            # Try converting from flit and poetry
            for converter in (flit, poetry):
                if converter.check_fingerprint(None, self._path):
                    metadata, settings = converter.convert(None, self._path, None)
                    data["project"] = metadata
                    if settings:
                        data.setdefault("tool", {}).setdefault("pdm", {}).update(
                            settings
                        )
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
        if not self.is_valid:
            raise ProjectError("No [project] table found in pyproject.toml")
        return self._data["project"]

    @property
    def settings(self) -> items.Table:
        return self._data.setdefault("tool", {}).setdefault("pdm", {})

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
            "overrides": self.settings.get("overrides", {}),
        }
        pyproject_content = json.dumps(dump_data, sort_keys=True)
        hasher = hashlib.new(algo)
        hasher.update(pyproject_content.encode("utf-8"))
        return hasher.hexdigest()
