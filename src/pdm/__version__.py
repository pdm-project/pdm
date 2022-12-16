import importlib.resources

from pdm.compat import importlib_metadata


def read_version() -> str:
    try:
        return importlib_metadata.version(__package__ or "pdm")
    except importlib_metadata.PackageNotFoundError:
        return importlib.resources.read_text("pdm.models", "VERSION").strip()


__version__ = read_version()
