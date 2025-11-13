from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import tomlkit

from pdm import termui
from pdm.compat import tomllib


class TOMLFile:
    def __init__(self, path: str | Path, *, parse: bool = True, ui: termui.UI) -> None:
        self._path = Path(path)
        self.ui = ui
        self._data = self._parse() if parse else {}
        self._for_write = False

    def _parse(self) -> dict[str, Any]:
        try:
            with self._path.open("rb") as fp:
                return tomllib.load(fp)
        except FileNotFoundError:
            return {}

    def open_for_write(self) -> tomlkit.TOMLDocument:
        # Ensure the document is parsed by tomlkit for writing with styles preserved
        if self._for_write:
            return cast(tomlkit.TOMLDocument, self._data)
        try:
            with self._path.open("rb") as fp:
                self._data = tomlkit.load(fp)
        except FileNotFoundError:
            self._data = tomlkit.document()
        self._for_write = True
        return self._data

    def open_for_read(self) -> dict[str, Any]:
        """Get the (read-only) data of the TOML file."""
        if hasattr(self._data, "unwrap"):
            return self._data.unwrap()  # type: ignore[attr-defined]
        return deepcopy(self._data)

    def set_data(self, data: dict[str, Any]) -> None:
        """Set the data of the TOML file."""
        self._data = data
        self._for_write = True

    def reload(self) -> None:
        self._data = self._parse()
        self._for_write = False

    def write(self) -> None:
        if not self._for_write:
            raise RuntimeError("TOMLFile not opened for write. Call open_for_write() first.")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as fp:
            tomlkit.dump(self._data, fp)

    def exists(self) -> bool:
        return self._path.exists()

    def empty(self) -> bool:
        return not self._data
