from __future__ import annotations

import sys

from packaging.version import Version, parse

if sys.version_info >= (3, 8):
    import importlib.metadata as importlib_metadata
else:
    import importlib_metadata


try:
    __version__ = importlib_metadata.version(__package__)
    parsed_version: Version | None = parse(__version__)
except importlib_metadata.PackageNotFoundError:
    __version__ = "UNKNOWN"
    parsed_version = None
