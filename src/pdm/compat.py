import importlib.resources
import sys
from pathlib import Path
from typing import BinaryIO, ContextManager

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


if sys.version_info >= (3, 9):

    def importlib_open_binary(package: str, resource: str) -> BinaryIO:
        return (importlib.resources.files(package) / resource).open("rb")

    def importlib_read_text(
        package: str, resource: str, encoding: str = "utf-8", errors: str = "strict"
    ) -> str:
        with (importlib.resources.files(package) / resource).open(
            "r", encoding=encoding, errors=errors
        ) as f:
            return f.read()

    def importlib_path(package: str, resource: str) -> ContextManager[Path]:
        return importlib.resources.as_file(
            importlib.resources.files(package) / resource
        )

else:
    importlib_open_binary = importlib.resources.open_binary
    importlib_read_text = importlib.resources.read_text
    importlib_path = importlib.resources.path


if sys.version_info >= (3, 8):
    from functools import cached_property
    from typing import Literal, Protocol, TypedDict
else:
    from typing import Any, Callable, Generic, TypeVar, overload

    from typing_extensions import Literal, Protocol, TypedDict

    _T = TypeVar("_T")
    _C = TypeVar("_C")

    class cached_property(Generic[_T]):
        def __init__(self, func: Callable[[Any], _T]):
            self.func = func
            self.attr_name = func.__name__
            self.__doc__ = func.__doc__

        @overload
        def __get__(self: _C, inst: None, cls: Any = ...) -> _C:
            ...

        @overload
        def __get__(self, inst: object, cls: Any = ...) -> _T:
            ...

        def __get__(self, inst, cls=None):
            if inst is None:
                return self
            if self.attr_name not in inst.__dict__:
                inst.__dict__[self.attr_name] = self.func(inst)
            return inst.__dict__[self.attr_name]


if sys.version_info >= (3, 10):
    import importlib.metadata as importlib_metadata
else:
    import importlib_metadata


Distribution = importlib_metadata.Distribution


__all__ = [
    "tomllib",
    "cached_property",
    "importlib_metadata",
    "Literal",
    "Protocol",
    "TypedDict",
    "Distribution",
]
