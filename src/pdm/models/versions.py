from __future__ import annotations

import re
from typing import Any, Union, overload

from pdm.compat import Literal
from pdm.exceptions import InvalidPyVersion

VersionBit = Union[int, Literal["*"]]  # noqa: F722
PRE_RELEASE_SEGMENT_RE = re.compile(
    r"(?P<digit>\d+)(?P<type>a|b|rc)(?P<n>\d*)",
    flags=re.IGNORECASE,
)


class Version:
    """A loosely semantic version implementation that allows '*' in version part.

    This class is designed for Python specifier set merging only, hence up to 3 version
    parts are kept, plus optional prerelease suffix.

    This is a slightly different purpose than packaging.version.Version which is
    focused on supporting PEP 440 version identifiers, not specifiers.
    """

    MIN: Version
    MAX: Version
    # Pre-release may follow version with {a|b|rc}N
    # https://docs.python.org/3/faq/general.html#how-does-the-python-version-numbering-scheme-work
    pre: tuple[str, int] | None = None

    def __init__(self, version: tuple[VersionBit, ...] | str) -> None:
        if isinstance(version, str):
            version_str = re.sub(r"(?<!\.)\*", ".*", version)
            bits: list[VersionBit] = []
            for v in version_str.split(".")[:3]:
                try:
                    bits.append(int(v))
                except ValueError:
                    pre_m = PRE_RELEASE_SEGMENT_RE.match(v)
                    if v == "*":
                        bits.append("*")
                        break  # .* is only allowed at the end, per PEP 440
                    elif pre_m:
                        bits.append(int(pre_m.group("digit")))
                        pre_type = pre_m.group("type").lower()
                        pre_n = int(pre_m.group("n") or "0")
                        self.pre = (pre_type, pre_n)
                        break  # pre release version is only at the end
                    else:
                        raise InvalidPyVersion(
                            f"{version_str}: postreleases are not supported for python version specifiers."
                        ) from None
            version = tuple(bits)
        self._version: tuple[VersionBit, ...] = version

    def complete(self, complete_with: VersionBit = 0, max_bits: int = 3) -> Version:
        """
        Complete the version with the given bit if the version has less than max parts
        """
        assert len(self._version) <= max_bits, self
        new_tuple = self._version + (max_bits - len(self._version)) * (complete_with,)
        ret = type(self)(new_tuple)
        ret.pre = self.pre
        return ret

    def bump(self, idx: int = -1) -> Version:
        """Bump version by incrementing 1 on the given index of version part.
        If index is not provided: increment the last version bit unless version
        is a pre-release, in which case, increment the pre-release number.
        """
        version = self._version
        if idx == -1 and self.pre:
            ret = type(self)(version).complete()
            ret.pre = (self.pre[0], self.pre[1] + 1)
        else:
            head, value = version[:idx], int(version[idx])
            ret = type(self)((*head, value + 1)).complete()
            ret.pre = None
        return ret

    def startswith(self, other: Version) -> bool:
        """Check if the version begins with another version."""
        return self._version[: len(other._version)] == other._version

    @property
    def is_wildcard(self) -> bool:
        """Check if the version ends with a '*'"""
        return self._version[-1] == "*"

    @property
    def is_prerelease(self) -> bool:
        """Check if the version is a prerelease."""
        return self.pre is not None

    def __str__(self) -> str:
        parts = []
        parts.append(".".join(map(str, self._version)))

        if self.pre:
            parts.append("".join(str(x) for x in self.pre))

        return "".join(parts)

    def __repr__(self) -> str:
        return f"<Version({self})>"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self._version == other._version and self.pre == other.pre

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, Version):
            return NotImplemented

        def comp_key(version: Version) -> list[float]:
            ret: list[float] = [-1 if v == "*" else v for v in version._version]
            if version.pre:
                # Get the ascii value of first character, a < b < r[c]
                ret += [ord(version.pre[0][0]), version.pre[1]]
            else:
                ret += [float("inf")]

            return ret

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
    def __getitem__(self, idx: slice) -> Version:
        ...

    def __getitem__(self, idx: int | slice) -> VersionBit | Version:
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
        return hash((self._version, self.pre))

    @property
    def is_py2(self) -> bool:
        return self._version[0] == 2


Version.MIN = Version((-1, -1, -1))
Version.MAX = Version((99, 99, 99))
