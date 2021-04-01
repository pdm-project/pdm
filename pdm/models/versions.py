import re
from typing import Any, Tuple, Union, cast, overload

from pdm._types import Literal
from pdm.exceptions import InvalidPyVersion

VersionBit = Union[int, Literal["*"]]


class Version:
    """A loosely semantic version implementation that allows '*' in version part.

    This class is designed for Python specifier set merging only, hence up to 3 version
    parts are kept, plus prereleases or postreleases are not supported.
    """

    MIN: "Version"
    MAX: "Version"

    def __init__(self, version: Union[Tuple[VersionBit, ...], str]) -> None:
        if isinstance(version, str):
            version_str = re.sub(r"(?<!\.)\*", ".*", version)
            try:
                version = cast(
                    Tuple[VersionBit, ...],
                    tuple(int(v) if v != "*" else v for v in version_str.split("."))[
                        :3
                    ],
                )
            except ValueError:
                raise InvalidPyVersion(
                    f"{version_str}: Prereleases or postreleases are not supported "
                    "for python version specifers."
                )
        self._version: Tuple[VersionBit, ...] = version

    def complete(self, complete_with: VersionBit = 0, max_bits: int = 3) -> "Version":
        """
        Complete the version with the given bit if the version has less than max parts
        """
        assert len(self._version) <= max_bits, self
        new_tuple = self._version + (max_bits - len(self._version)) * (complete_with,)
        return type(self)(new_tuple)

    def bump(self, idx: int = -1) -> "Version":
        """Bump version by incrementing 1 on the given index of version part.
        Increment the last version bit by default.
        """
        version = self._version
        head, value = version[:idx], int(version[idx])
        return type(self)((*head, value + 1)).complete()

    def startswith(self, other: "Version") -> bool:
        """Check if the version begins with another version."""
        return self._version[: len(other._version)] == other._version

    @property
    def is_wildcard(self) -> bool:
        """Check if the version ends with a '*'"""
        return self._version[-1] == "*"

    def __str__(self) -> str:
        return ".".join(map(str, self._version))

    def __repr__(self) -> str:
        return f"<Version({self})>"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self._version == other._version

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, Version):
            return NotImplemented

        def comp_key(version: Version) -> Tuple[int, ...]:
            return tuple(-1 if v == "*" else v for v in version._version)

        return comp_key(self) < comp_key(other)

    def __gt__(self, other: Any) -> bool:
        return not (self.__lt__(other) or self.__eq__(other))

    def __le__(self, other: Any) -> bool:
        return self.__lt__(other) or self.__eq__(other)

    def __ge__(self, other: Any) -> bool:
        return self.__gt__(other) or self.__eq__(other)

    @overload
    def __getitem__(self, idx: int) -> VersionBit:
        ...

    @overload
    def __getitem__(self, idx: slice) -> "Version":
        ...

    def __getitem__(self, idx: Union[int, slice]) -> Union[VersionBit, "Version"]:
        if isinstance(idx, slice):
            return type(self)(self._version[idx])
        else:
            return self._version[idx]

    def __setitem__(self, idx: int, value: VersionBit) -> None:
        if not isinstance(idx, int):
            raise TypeError("Slice assignment is not supported")
        version = list(self._version)
        version[idx] = value
        self._version = tuple(version)

    def __hash__(self) -> int:
        return hash(self._version)

    @property
    def is_py2(self) -> bool:
        return self._version[0] == 2


Version.MIN = Version((-1, -1, -1))
Version.MAX = Version((99, 99, 99))
