from __future__ import annotations

import abc
import os
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
        line = req.replace("file:///${PROJECT_ROOT}", self.root.as_uri())
        if expand_env:
            line = expand_env_vars(line)
        return line

    def relative_path_to_url(self, path: str) -> str:
        if os.path.isabs(path):
            return Path(path).as_uri()
        return f"file:///${{PROJECT_ROOT}}/{urllib.parse.quote(path)}"

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
    if url.startswith("file:///${PROJECT_ROOT}"):
        return urllib.parse.unquote(url[len("file:///${PROJECT_ROOT}/") :])
    if url.startswith("{root:uri}"):
        return urllib.parse.unquote(url[len("{root:uri}/") :])
    return None
