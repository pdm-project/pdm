from __future__ import annotations

import importlib.resources
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO, ContextManager, Sequence

if TYPE_CHECKING:
    from pdm.models.requirements import Requirement

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


if (
    sys.version_info >= (3, 9) and not (sys.version_info[:2] == (3, 9) and sys.platform == "win32")
    # a bug on windows+py39 that zipfile path is not normalized
):

    def resources_open_binary(package: str, resource: str) -> BinaryIO:
        return (importlib.resources.files(package) / resource).open("rb")

    def resources_read_text(package: str, resource: str, encoding: str = "utf-8", errors: str = "strict") -> str:
        with (importlib.resources.files(package) / resource).open("r", encoding=encoding, errors=errors) as f:
            return f.read()

    def resources_path(package: str, resource: str) -> ContextManager[Path]:
        return importlib.resources.as_file(importlib.resources.files(package) / resource)

else:
    resources_open_binary = importlib.resources.open_binary
    resources_read_text = importlib.resources.read_text
    resources_path = importlib.resources.path


if sys.version_info >= (3, 10):
    import importlib.metadata as importlib_metadata
else:
    import importlib_metadata


if sys.version_info >= (3, 9):
    import importlib.resources as importlib_resources
else:
    import importlib_resources


Distribution = importlib_metadata.Distribution


class CompatibleSequence(Sequence["Requirement"]):  # pragma: no cover
    """A compatibility class for Sequence that also exposes `items()`, `keys()` and `values()` methods"""

    def __init__(self, data: Sequence[Requirement]) -> None:
        self._data = data

    def __getitem__(self, index: int) -> Requirement:  # type: ignore[override]
        return self._data[index]

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self) -> Iterator[Requirement]:
        return iter(self._data)

    def keys(self) -> Sequence[str]:
        from pdm.utils import deprecation_warning

        deprecation_warning(
            ".keys() is deprecated on the requirements collection, it's not a mapping anymore.", stacklevel=2
        )
        return [r.identify() for r in self._data]

    def values(self) -> Sequence[Requirement]:
        from pdm.utils import deprecation_warning

        deprecation_warning(
            ".values() is deprecated on the requirements collection, it's not a mapping anymore.", stacklevel=2
        )
        return self._data

    def items(self) -> Iterator[tuple[str, Requirement]]:
        from pdm.utils import deprecation_warning

        deprecation_warning(
            ".items() is deprecated on the requirements collection, it's not a mapping anymore.", stacklevel=2
        )
        for r in self._data:
            yield r.identify(), r


__all__ = ["tomllib", "importlib_metadata", "Distribution", "importlib_resources", "CompatibleSequence"]
