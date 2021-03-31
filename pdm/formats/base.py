from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

import tomlkit
from tomlkit.items import Array, InlineTable

from pdm import termui


def convert_from(
    field: str = None, name: str = None
) -> Callable[
    [Callable[[MetaConverter, Any], Any]], Callable[[MetaConverter, Any], Any]
]:
    def wrapper(
        func: Callable[[MetaConverter, Any], Any]
    ) -> Callable[[MetaConverter, Any], Any]:
        func._convert_from = field
        func._convert_to = name
        return func

    return wrapper


class Unset(Exception):
    pass


class _MetaConverterMeta(type):
    def __init__(cls, name: str, bases: Tuple[type], ns: Dict[str, Any]) -> None:
        super().__init__(name, bases, ns)
        cls._converters = {}
        _default = object()
        for key, value in ns.items():
            if getattr(value, "_convert_from", _default) is not _default:
                name = value._convert_to or key
                cls._converters[name] = value


class MetaConverter(metaclass=_MetaConverterMeta):
    """Convert a metadata dictionary to PDM's format"""

    def __init__(self, source: dict, ui: Optional[termui.UI] = None) -> None:
        self.source = source
        self.settings = {}
        self._data = {}
        self._ui = ui

    def convert(self) -> Tuple[Mapping, Mapping]:
        source = self.source
        for key, func in self._converters.items():
            if func._convert_from and func._convert_from not in source:
                continue
            if func._convert_from is None:
                value = source
            else:
                value = source[func._convert_from]
            try:
                self._data[key] = func(self, value)
            except Unset:
                pass

        # Delete all used fields
        for key, func in self._converters.items():
            if func._convert_from is None:
                continue
            try:
                del source[func._convert_from]
            except KeyError:
                pass
        # Add remaining items to the data
        self._data.update(source)
        return self._data, self.settings


NAME_EMAIL_RE = re.compile(r"(?P<name>[^,]+?)\s*<(?P<email>.+)>\s*$")


def make_inline_table(data: Mapping) -> InlineTable:
    """Create an inline table from the given data."""
    table = tomlkit.inline_table()
    table.update(data)
    return table


def make_array(data: list, multiline: bool = False) -> Array:
    if not data:
        return []
    array = tomlkit.array()
    array.multiline(multiline)
    for item in data:
        array.append(item)
    return array


def array_of_inline_tables(value: List[Mapping], multiline: bool = True) -> Array:
    return make_array([make_inline_table(item) for item in value], multiline)


def parse_name_email(name_email: List[str]) -> Array:
    return array_of_inline_tables(
        [NAME_EMAIL_RE.match(item).groupdict() for item in name_email]
    )
