from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from findpython import PythonVersion
from packaging.version import InvalidVersion, Version

from pdm.compat import cached_property


class PythonInfo:
    """
    A convenient helper class that holds all information of a Python interepreter.
    """

    def __init__(self, py_version: PythonVersion) -> None:
        self._py_ver = py_version

    @classmethod
    def from_path(cls, path: str | Path) -> PythonInfo:
        py_ver = PythonVersion(Path(path))
        return cls(py_ver)

    @cached_property
    def valid(self) -> bool:
        return self._py_ver.executable.exists() and self._py_ver.is_valid()

    def __hash__(self) -> int:
        return hash(self._py_ver)

    def __eq__(self, o: Any) -> bool:
        if not isinstance(o, PythonInfo):
            return False
        return self.path == o.path

    @property
    def path(self) -> Path:
        return self._py_ver.executable

    @property
    def executable(self) -> Path:
        return self._py_ver.interpreter

    @property
    def version(self) -> Version:
        return self._py_ver.version

    @property
    def major(self) -> int:
        return self._py_ver.major

    @property
    def minor(self) -> int:
        return self._py_ver.minor

    @property
    def micro(self) -> int:
        return self._py_ver.patch

    @property
    def version_tuple(self) -> tuple[int, ...]:
        return (self.major, self.minor, self.micro)

    @property
    def is_32bit(self) -> bool:
        return "32bit" in self._py_ver.architecture

    def for_tag(self) -> str:
        return f"{self.major}{self.minor}"

    @property
    def identifier(self) -> str:
        try:
            if os.name == "nt" and self.is_32bit:
                return f"{self.major}.{self.minor}-32"
            return f"{self.major}.{self.minor}"
        except InvalidVersion:
            return "unknown"
