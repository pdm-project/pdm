import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


if sys.version_info >= (3, 8):
    from typing import Literal, Protocol, TypedDict
else:
    from typing_extensions import Literal, Protocol, TypedDict

if sys.version_info >= (3, 10):
    import importlib.metadata as importlib_metadata
else:
    import importlib_metadata


Distribution = importlib_metadata.Distribution


__all__ = [
    "tomllib",
    "importlib_metadata",
    "Literal",
    "Protocol",
    "TypedDict",
    "Distribution",
]
