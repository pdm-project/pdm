from __future__ import annotations

import abc
import os
import sys
import urllib.parse
from pathlib import Path
from typing import TYPE_CHECKING

from pdm.utils import expand_env_vars

if TYPE_CHECKING:
    from typing import TypedDict

    BuildSystem = TypedDict("BuildSystem", {"requires": list[str], "build-backend": str})


class BuildBackend(metaclass=abc.ABCMeta):
    """A build backend that does not support dynamic values in dependencies"""

    def __init__(self, root: Path) -> None:
        self.root = root

    def expand_line(self, line: str, expand_env: bool = True) -> str:
        return line

    def relative_path_to_url(self, path: str) -> str:
        return self.root.joinpath(path).as_uri()

    @classmethod
    @abc.abstractmethod
    def build_system(cls) -> BuildSystem:
        pass


class FlitBackend(BuildBackend):
    @classmethod
    def build_system(cls) -> BuildSystem:
        return {
            "requires": ["flit_core>=3.2,<4"],
            "build-backend": "flit_core.buildapi",
        }


class SetuptoolsBackend(BuildBackend):
    @classmethod
    def build_system(cls) -> BuildSystem:
        return {
            "requires": ["setuptools>=61"],
            "build-backend": "setuptools.build_meta",
        }


class PDMBackend(BuildBackend):
    def expand_line(self, req: str, expand_env: bool = True) -> str:
        from pdm.termui import logger

        root_uri = self.root.as_uri()
        logger.debug(f"expand_line: Original req: {req}")
        logger.debug(f"expand_line: root_uri: {root_uri}")
        logger.debug(f"expand_line: self.root: {self.root}")

        # Special Windows handling to ensure proper path expansion
        if "PROJECT_ROOT" in req and sys.platform == "win32":
            logger.debug("expand_line: Windows-specific PROJECT_ROOT handling")

            # First replace PROJECT_ROOT with a special marker that won't be affected by env var expansion
            temp_marker = "___PDM_PROJECT_ROOT_TEMP_MARKER___"
            line_with_marker = req.replace("${PROJECT_ROOT}", temp_marker)

            # Then handle any environment variable expansion
            if expand_env:
                line_with_marker = expand_env_vars(line_with_marker)

            # Finally replace the marker with the actual root URI
            if "file:///" + temp_marker in line_with_marker:
                # Handle file URL format
                line = line_with_marker.replace("file:///" + temp_marker, root_uri[len("file:///") :])
                logger.debug(f"expand_line: Windows PROJECT_ROOT in file URL replaced: {line}")
            else:
                # Normal environment variable replacement
                line = line_with_marker.replace(temp_marker, str(self.root))
                logger.debug(f"expand_line: Windows PROJECT_ROOT in path replaced: {line}")

            # Now replace file:///${PROJECT_ROOT} with the root URI (this handles URLs that weren't caught above)
            if "file:///${PROJECT_ROOT}" in line:
                line = line.replace("file:///${PROJECT_ROOT}", root_uri)
                logger.debug(f"expand_line: Windows file:///${{PROJECT_ROOT}} replaced: {line}")

            return line

        # Default handling for non-Windows or when PROJECT_ROOT isn't in the string
        # Replace project root placeholder with actual URI
        line = req.replace("file:///${PROJECT_ROOT}", root_uri)
        logger.debug(f"expand_line: After PROJECT_ROOT replacement: {line}")

        if expand_env:
            before_expand = line
            line = expand_env_vars(line)
            if before_expand != line:
                logger.debug(f"expand_line: After env var expansion: {line}")

        return line

    def relative_path_to_url(self, path: str) -> str:
        from pdm.termui import logger

        logger.debug(f"relative_path_to_url: Input path: {path}, isabs={os.path.isabs(path)}")

        if os.path.isabs(path):
            uri = Path(path).as_uri()
            logger.debug(f"relative_path_to_url: Absolute path URI: {uri}")
            return uri

        # Use platform-appropriate path for Windows
        if sys.platform == "win32":
            # Need to normalize Windows path separators without using backslash in f-string
            normalized_path = path.replace("\\", "/")
            if normalized_path != path:
                logger.debug(f"relative_path_to_url: Normalized Windows path: {path} -> {normalized_path}")

            quoted_path = urllib.parse.quote(normalized_path)
            url = f"file:///${{PROJECT_ROOT}}/{quoted_path}"
            logger.debug(f"relative_path_to_url: Windows URL result: {url}")
            return url

        quoted_path = urllib.parse.quote(path)
        url = f"file:///${{PROJECT_ROOT}}/{quoted_path}"
        logger.debug(f"relative_path_to_url: Unix URL result: {url}")
        return url

    @classmethod
    def build_system(cls) -> BuildSystem:
        return {
            "requires": ["pdm-backend"],
            "build-backend": "pdm.backend",
        }


# Context formatting helpers for hatch
class PathContext:
    def __init__(self, path: Path) -> None:
        self.__path = path

    def __format__(self, __format_spec: str) -> str:
        if not __format_spec:
            return self.__path.as_posix()
        elif __format_spec == "uri":
            return self.__path.as_uri()
        elif __format_spec == "real":
            return self.__path.resolve().as_posix()
        raise ValueError(f"Unknown format specifier: {__format_spec}")


class EnvContext:
    def __init__(self, expand: bool = True) -> None:
        self.expand = expand

    def __format__(self, __format_spec: str) -> str:
        name, sep, default = __format_spec.partition(":")
        if not self.expand:
            return f"${{{name}}}"
        if name in os.environ:
            return os.environ[name]
        if not sep:
            raise ValueError(f"Nonexistent environment variable must set a default: {name}")
        return default


class HatchBackend(BuildBackend):
    def expand_line(self, line: str, expand_env: bool = True) -> str:
        return line.format(
            env=EnvContext(expand=expand_env),
            root=PathContext(self.root),
            home=PathContext(Path.home()),
        )

    def relative_path_to_url(self, path: str) -> str:
        if os.path.isabs(path):
            return Path(path).as_uri()
        return f"{{root:uri}}/{urllib.parse.quote(path)}"

    @classmethod
    def build_system(cls) -> BuildSystem:
        return {
            "requires": ["hatchling"],
            "build-backend": "hatchling.build",
        }


_BACKENDS: dict[str, type[BuildBackend]] = {
    "pdm-backend": PDMBackend,
    "setuptools": SetuptoolsBackend,
    "flit-core": FlitBackend,
    "hatchling": HatchBackend,
}
# Fallback to the first backend
DEFAULT_BACKEND = next(iter(_BACKENDS.values()))


def get_backend(name: str) -> type[BuildBackend]:
    """Get the build backend class by name"""
    return _BACKENDS[name]


def get_backend_by_spec(spec: dict) -> type[BuildBackend]:
    """Get the build backend class by specification.
    The parameter passed in is the 'build-system' section in pyproject.toml.
    """
    if "build-backend" not in spec:
        return DEFAULT_BACKEND
    for backend_cls in _BACKENDS.values():
        if backend_cls.build_system()["build-backend"] == spec["build-backend"]:
            return backend_cls
    return DEFAULT_BACKEND


def get_relative_path(url: str) -> str | None:
    from pdm.termui import logger

    logger.debug(f"get_relative_path: Input URL: {url}")

    if url.startswith("file:///${PROJECT_ROOT}"):
        relpath = urllib.parse.unquote(url[len("file:///${PROJECT_ROOT}/") :])
        logger.debug(f"get_relative_path: Extracted from PROJECT_ROOT URL: {relpath}")
        return relpath
    if url.startswith("{root:uri}"):
        relpath = urllib.parse.unquote(url[len("{root:uri}/") :])
        logger.debug(f"get_relative_path: Extracted from root:uri URL: {relpath}")
        return relpath

    # Windows-specific handling for paths with drive letters
    if sys.platform == "win32" and url.startswith("file:///"):
        # Check if it looks like a Windows path with a drive letter
        path = urllib.parse.unquote(url[len("file:///") :])
        if len(path) >= 2 and path[1] == ":":
            logger.debug(f"get_relative_path: Found absolute Windows path: {path}")
            # This is an absolute path with a drive letter, not a relative path
            return None

    logger.debug(f"get_relative_path: Not a relative path URL pattern: {url}")
    return None
