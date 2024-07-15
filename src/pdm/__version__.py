from pdm.compat import importlib_metadata, resources_read_text


def read_version() -> str:
    try:
        return importlib_metadata.version(__package__ or "pdm")
    except importlib_metadata.PackageNotFoundError:
        return resources_read_text("pdm.models", "VERSION").strip()


__version__ = read_version()
