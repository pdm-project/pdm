from __future__ import annotations

import re
import sys
from collections.abc import Mapping, MutableMapping
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import tomlkit

from pdm import termui
from pdm.compat import tomllib
from pdm.utils import atomic_open_for_write, deprecation_warning

if TYPE_CHECKING:
    from types import FrameType


def _same(left: Any, right: Any) -> bool:
    """Compare two plain TOML values. Unlike ``==``, it tells ``1``, ``1.0`` and ``True`` apart."""
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return left.keys() == right.keys() and all(_same(value, right[key]) for key, value in left.items())
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(map(_same, left, right))
    return type(left) is type(right) and left == right


def _sync_table(target: MutableMapping[str, Any], source: Mapping[str, Any]) -> None:
    """Make the tomlkit table ``target`` hold the same data as ``source``, touching only the values
    that differ so that the comments and the formatting of everything else are preserved.
    """
    for key in [key for key in target if key not in source]:
        del target[key]
    for key, value in source.items():
        if key not in target:
            target[key] = value
            continue
        current = target[key]
        if isinstance(current, MutableMapping) and isinstance(value, Mapping):
            _sync_table(current, value)
        elif not _same(current.unwrap() if hasattr(current, "unwrap") else current, value):
            target[key] = value


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

    def _merge_into_document(self) -> tomlkit.TOMLDocument:
        """Apply the data that was modified without ``open_for_write()`` to the document on disk."""
        try:
            doc = self._file.read()
            _sync_table(doc, self._data)
            if _same(tomllib.loads(doc.as_string()), self._data):
                return doc
            termui.logger.debug("Updating %s in place gives different data", self._path)
        except Exception as e:
            termui.logger.debug("Failed to update %s in place: %r", self._path, e)
        # The document can't be edited in place reliably, write the data without the original styles.
        doc = tomlkit.document()
        doc.update(self._data)
        return doc

    def write(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._for_write:
            # Compatibility for callers that modify the data returned by the read-only parser.
            # The data stays as it is, since the caller may still hold references to it.
            stacklevel = 2
            frame: FrameType | None = sys._getframe(1)
            while frame is not None and frame.f_globals.get("__name__", "").startswith("pdm.project."):
                # Point the warning at the caller, not at the write() of a subclass
                stacklevel += 1
                frame = frame.f_back
            deprecation_warning(
                f"Writing {self._path.name} without calling open_for_write() first is deprecated, "
                "call it before modifying the data.",
                stacklevel=stacklevel,
            )
            data = self._merge_into_document()
        elif isinstance(self._data, tomlkit.TOMLDocument):
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
