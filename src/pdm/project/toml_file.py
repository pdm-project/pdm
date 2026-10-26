from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import tomlkit

from pdm import termui
from pdm.compat import tomllib
from pdm.utils import atomic_open_for_write


class TOMLFile:
    def __init__(self, path: str | Path, *, parse: bool = True, ui: termui.UI) -> None:
        from tomlkit.toml_file import TOMLFile as TomlkitTOMLFile

        self._file = TomlkitTOMLFile(path)
        self.ui = ui
        self._data = self._parse() if parse else {}
        self._for_write = False

    @property
    def _path(self) -> Path:
        return Path(self._file._path)

    def _parse(self) -> dict[str, Any]:
        # By default, use tomllib for parsing as it is much faster
        try:
            with open(self._path, "rb") as fp:
                return tomllib.load(fp)
        except FileNotFoundError:
            return {}

    def open_for_write(self) -> tomlkit.TOMLDocument:
        # Ensure the document is re-parsed by tomlkit for writing with styles preserved
        if self._for_write:
            return cast(tomlkit.TOMLDocument, self._data)
        try:
            self._data = self._file.read()
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
        if isinstance(self._data, tomlkit.TOMLDocument):
            data = self._data
        else:
            data = tomlkit.document()
            data.update(self._data)
        content = data.as_string()
        if self._file._linesep == "\n":
            content = content.replace("\r\n", "\n")
        elif self._file._linesep == "\r\n":
            content = re.sub(r"(?<!\r)\n", "\r\n", content)
        with atomic_open_for_write(self._path, encoding="utf-8", newline="") as fp:
            fp.write(content)

    def exists(self) -> bool:
        return self._path.exists()

    def empty(self) -> bool:
        return not self._data
