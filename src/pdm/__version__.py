from pdm.compat import importlib_metadata


def read_version() -> str:
    return importlib_metadata.version(__package__ or "pdm")


try:
    __version__ = read_version()
except importlib_metadata.PackageNotFoundError:
    __version__ = "0.0.0+local"
