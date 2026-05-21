from __future__ import annotations

import sys
from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from typing import Protocol

    class SupportsIdentify(Protocol):
        def identify(self) -> str: ...


if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

T = TypeVar("T", bound="SupportsIdentify")


class CompatibleSequence(Sequence[T]):  # pragma: no cover
    """A compatibility class for Sequence that also exposes `items()`, `keys()` and `values()` methods"""

    def __init__(self, data: Sequence[T]) -> None:
        self._data = data

    def __getitem__(self, index: str | slice | int) -> T | Sequence[T]:  # type: ignore[override]
        if isinstance(index, str):
            from pdm.utils import deprecation_warning

            deprecation_warning(
                "__getitem__ with a string key is deprecated on the requirements collection. It's not a mapping but a list",
                stacklevel=2,
            )
            for r in self._data:
                if r.identify() == index:
                    return r
            raise KeyError(index)
        return self._data[index]

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self) -> Iterator[T]:
        return iter(self._data)

    def keys(self) -> Sequence[str]:
        from pdm.utils import deprecation_warning

        deprecation_warning(
            ".keys() is deprecated on the requirements collection, it's not a mapping but a list.", stacklevel=2
        )
        return [r.identify() for r in self._data]

    def values(self) -> Sequence[T]:
        from pdm.utils import deprecation_warning

        deprecation_warning(
            ".values() is deprecated on the requirements collection, it's not a mapping but a list.", stacklevel=2
        )
        return self._data

    def items(self) -> Iterator[tuple[str, T]]:
        from pdm.utils import deprecation_warning

        deprecation_warning(
            ".items() is deprecated on the requirements collection, it's not a mapping anymore.", stacklevel=2
        )
        for r in self._data:
            yield r.identify(), r


__all__ = ["CompatibleSequence", "tomllib"]
