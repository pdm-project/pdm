from __future__ import annotations

from packaging.version import Version, parse

from pdm.compat import importlib_metadata


def read_version() -> str:
    return importlib_metadata.version(__package__)


try:
    __version__ = read_version()
    parsed_version: Version | None = parse(__version__)
except importlib_metadata.PackageNotFoundError:
    __version__ = "UNKNOWN"
    parsed_version = None
