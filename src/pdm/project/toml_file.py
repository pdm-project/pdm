from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import tomlkit
from tomlkit.toml_document import TOMLDocument
from tomlkit.toml_file import TOMLFile

from pdm import termui


class TOMLBase(TOMLFile):
    def __init__(self, path: str | Path, *, ui: termui.UI) -> None:
        super().__init__(path)
        self._path = Path(path)
        self.ui = ui
        self._data = self.read()

    def read(self) -> TOMLDocument:
        if not self._path.exists():
            return tomlkit.document()
        return super().read()

    def set_data(self, data: Mapping[str, Any]) -> None:
        """Set the data of the TOML file."""
        self._data = tomlkit.document()
        self._data.update(data)

    def reload(self) -> None:
        self._data = self.read()

    def write(self) -> None:
        return super().write(self._data)

    @property
    def exists(self) -> bool:
        return self._path.exists()

    @property
    def empty(self) -> bool:
        return not self._data
