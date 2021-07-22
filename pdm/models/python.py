from __future__ import annotations

import dataclasses
import os
from pathlib import Path
from typing import Any

from packaging.version import Version
from pythonfinder import InvalidPythonVersion
from pythonfinder.models.python import PythonVersion

from pdm.exceptions import InvalidPyVersion
from pdm.models.in_process import get_architecture, get_underlying_executable
from pdm.utils import cached_property


@dataclasses.dataclass
class PythonInfo:
    """
    A convenient helper class that holds all information of a Python interepreter.
    """

    path: str
    version: Version
    executable: str = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        executable = get_underlying_executable(self.path)
        self.executable = Path(executable).as_posix()

    @classmethod
    def from_python_version(cls, py_version: PythonVersion) -> "PythonInfo":
        return cls(path=py_version.executable, version=py_version.version)

    @classmethod
    def from_path(cls, path: str | Path) -> "PythonInfo":
        try:
            return cls.from_python_version(PythonVersion.from_path(str(path)))
        except InvalidPythonVersion as e:
            raise InvalidPyVersion(str(e)) from e

    def __hash__(self) -> int:
        return hash(os.path.normcase(self.executable))

    def __eq__(self, o: Any) -> bool:
        if not isinstance(o, PythonInfo):
            return False
        return os.path.normcase(self.executable) == os.path.normcase(o.executable)

    @property
    def major(self) -> int:
        return self.version.major

    @property
    def minor(self) -> int:
        return self.version.minor

    @property
    def micro(self) -> int:
        return self.version.micro

    @property
    def version_tuple(self) -> tuple[int, ...]:
        return (self.major, self.minor, self.micro)

    @cached_property
    def is_32bit(self) -> bool:
        return "32bit" in get_architecture(self.executable)

    def for_tag(self) -> str:
        return f"{self.major}{self.minor}"

    @property
    def identifier(self) -> str:
        if os.name == "nt" and self.is_32bit:
            return f"{self.major}.{self.minor}-32"
        return f"{self.major}.{self.minor}"
