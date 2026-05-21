import importlib.metadata
import importlib.resources


def read_version() -> str:
    try:
        return importlib.metadata.version(__package__ or "pdm")
    except importlib.metadata.PackageNotFoundError:
        return importlib.resources.read_text("pdm", "VERSION").strip()


__version__ = read_version()
