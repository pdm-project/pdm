# For backward comaptibility purpose, export apis from pdm.pep517 here.
import warnings

from pdm.pep517.api import (  # noqa
    build_sdist,
    build_wheel,
    get_requires_for_build_sdist,
    get_requires_for_build_wheel,
    prepare_metadata_for_build_wheel,
)

warnings.warn(
    "`pdm.builders.api` is deprecated in favor of `pdm.pep517.api` and will be "
    "removed in the future. Please update the [build-system] settings in your"
    "pyproject.toml.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = (
    "get_requires_for_build_sdist",
    "get_requires_for_build_wheel",
    "build_sdist",
    "build_wheel",
    "prepare_metadata_for_build_wheel",
)
