from __future__ import annotations

from typing import Any, Callable, Mapping, TypeVar, cast

import tomlkit

from pdm import termui

_T = TypeVar("_T", bound=Callable)


def convert_from(field: str | None = None, name: str | None = None) -> Callable[[_T], _T]:
    def wrapper(func: _T) -> _T:
        func._convert_from = field  # type: ignore[attr-defined]
        func._convert_to = name  # type: ignore[attr-defined]
        return func

    return wrapper


class Unset(Exception):
    pass


class MetaConvertError(Exception):
    """A special exception that preserves the partial metadata that are already resolved."""

    def __init__(self, errors: list[str], *, data: dict[str, Any], settings: dict[str, Any]) -> None:
        self.errors = errors
        self.data = data
        self.settings = settings

    def __str__(self) -> str:
        return "\n" + "\n".join(self.errors)


class _MetaConverterMeta(type):
    def __init__(cls, name: str, bases: tuple[type, ...], ns: dict[str, Any]) -> None:
        super().__init__(name, bases, ns)
        cls._converters = {}
        _default = object()
        for key, value in ns.items():
            if getattr(value, "_convert_from", _default) is not _default:
                name = value._convert_to or key
                cls._converters[name] = value


class MetaConverter(metaclass=_MetaConverterMeta):
    """Convert a metadata dictionary to PDM's format"""

    _converters: dict[str, Callable]

    def __init__(self, source: dict, ui: termui.UI | None = None) -> None:
        self.source = source
        self.settings: dict[str, Any] = {}
        self._data: dict[str, Any] = {}
        self._ui = ui

    def convert(self) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        source = self.source
        errors: list[str] = []
        for key, func in self._converters.items():
            if func._convert_from and func._convert_from not in source:  # type: ignore[attr-defined]
                continue
            value = source if func._convert_from is None else source[func._convert_from]  # type: ignore[attr-defined]
            try:
                self._data[key] = func(self, value)
            except Unset:
                pass
            except Exception as e:
                errors.append(f"{key}: {e}")

        # Delete all used fields
        for func in self._converters.values():
            if func._convert_from is None:  # type: ignore[attr-defined]
                continue
            try:
                del source[func._convert_from]  # type: ignore[attr-defined]
            except KeyError:
                pass
        # Add remaining items to the data
        self._data.update(source)
        if errors:
            raise MetaConvertError(errors, data=self._data, settings=self.settings)
        return self._data, self.settings


def make_inline_table(data: Mapping) -> dict:
    """Create an inline table from the given data."""
    table = cast(dict, tomlkit.inline_table())
    table.update(data)
    return table


def make_array(data: list, multiline: bool = False) -> list:
    if not data:
        return []
    array = cast(list, tomlkit.array().multiline(multiline))
    array.extend(data)
    return array


def array_of_inline_tables(value: list[Mapping], multiline: bool = True) -> list[str]:
    return make_array([make_inline_table(item) for item in value], multiline)
