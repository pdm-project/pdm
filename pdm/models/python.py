import dataclasses
import os
from typing import Any, Tuple

from packaging.version import Version
from pythonfinder.models.python import PythonVersion

from pdm.models.in_process import get_architecture
from pdm.utils import cached_property


@dataclasses.dataclass
class PythonInfo:
    """
    A convenient helper class that holds all information of a Python interepreter.
    """

    executable: str
    version: Version

    @classmethod
    def from_python_version(cls, py_version: PythonVersion) -> "PythonInfo":
        return cls(executable=py_version.executable, version=py_version.version)

    @classmethod
    def from_path(cls, path: os.PathLike) -> "PythonInfo":
        return cls.from_python_version(PythonVersion.from_path(str(path)))

    def __hash__(self) -> int:
        return hash(os.path.normpath(self.executable))

    def __eq__(self, o: Any) -> bool:
        if not isinstance(o, PythonInfo):
            return False
        return os.path.normpath(self.executable) == os.path.normpath(o.executable)

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
    def version_tuple(self) -> Tuple[int, ...]:
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
