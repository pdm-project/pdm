from __future__ import annotations

import dataclasses
import itertools
import json
import re
import warnings
from functools import lru_cache
from operator import attrgetter
from typing import Any, Iterable, Match, cast

from dep_logic.specifiers import (
    BaseSpecifier,
    EmptySpecifier,
    RangeSpecifier,
    UnionSpecifier,
    VersionSpecifier,
    from_specifierset,
)
from packaging.specifiers import SpecifierSet

from pdm.exceptions import InvalidPyVersion
from pdm.models.versions import Version
from pdm.utils import parse_version


def _read_max_versions() -> dict[Version, int]:
    from pdm.compat import resources_open_binary

    with resources_open_binary("pdm.models", "python_max_versions.json") as fp:
        return {Version(k): v for k, v in json.load(fp).items()}


@lru_cache
def get_specifier(version_str: str | None) -> SpecifierSet:
    if not version_str or version_str == "*":
        return SpecifierSet()
    return SpecifierSet(version_str)


_legacy_specifier_re = re.compile(r"(==|!=|<=|>=|<|>)(\s*)([^,;\s)]*)")


@lru_cache
def fix_legacy_specifier(specifier: str) -> str:
    """Since packaging 22.0, legacy specifiers like '>=4.*' are no longer
    supported. We try to normalize them to the new format.
    """

    def fix_wildcard(match: Match[str]) -> str:
        operator, _, version = match.groups()
        if operator in ("==", "!="):
            return match.group(0)
        if ".*" in version:
            warnings.warn(".* suffix can only be used with `==` or `!=` operators", FutureWarning, stacklevel=4)
            version = version.replace(".*", ".0")
            if operator in ("<", "<="):  # <4.* and <=4.* are equivalent to <4.0
                operator = "<"
            elif operator in (">", ">="):  # >4.* and >=4.* are equivalent to >=4.0
                operator = ">="
        elif "+" in version:  # Drop the local version
            warnings.warn(
                "Local version label can only be used with `==` or `!=` operators", FutureWarning, stacklevel=4
            )
            version = version.split("+")[0]
        return f"{operator}{version}"

    return _legacy_specifier_re.sub(fix_wildcard, specifier)


class PySpecSet(SpecifierSet):
    """A custom SpecifierSet that supports merging with logic operators (&, |)."""

    PY_MAX_MINOR_VERSION = _read_max_versions()
    MAX_MAJOR_VERSION = max(PY_MAX_MINOR_VERSION)[:1].bump()

    __slots__ = ("_specs", "_logic", "_prereleases")

    def __init__(self, spec: str | VersionSpecifier = "") -> None:
        if spec == "<empty>":
            spec = EmptySpecifier()
        if isinstance(spec, BaseSpecifier):
            super().__init__(self._normalize(spec))
            self._logic = spec
            return
        try:
            if spec == "*":  # pragma: no cover
                spec = ""
            super().__init__(fix_legacy_specifier(spec))
            self._logic = from_specifierset(self)
        except ValueError:
            raise InvalidPyVersion(f"Invalid specifier: {spec}") from None

    def __hash__(self) -> int:
        return hash(self._logic)

    def __str__(self) -> str:
        if self.is_empty():
            return "<empty>"
        return super().__str__()

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, PySpecSet):
            return NotImplemented
        return self._logic == other._logic

    def is_empty(self) -> bool:
        """Check whether the specifierset contains any valid versions."""
        return self._logic.is_empty()

    def is_any(self) -> bool:
        """Return True if the specifierset accepts all versions."""
        return self._logic.is_any()

    @classmethod
    def _normalize(cls, spec: VersionSpecifier) -> str:
        if spec.is_empty():
            return ""
        if not isinstance(spec, UnionSpecifier):
            return str(spec)
        ranges, next_ranges = itertools.tee(sorted(spec.ranges))
        next(next_ranges, None)
        whole_range = RangeSpecifier(
            min=spec.ranges[0].min,
            max=spec.ranges[-1].max,
            include_min=spec.ranges[0].include_min,
            include_max=spec.ranges[-1].include_max,
        )
        parts = [] if whole_range.is_any() else [str(whole_range)]
        for left, right in zip(ranges, next_ranges):
            assert left.max is not None and right.min is not None
            start = Version(left.max.release).complete()
            end = Version(right.min.release).complete()
            if left.include_max:
                start = start.bump()
            if not right.include_min:
                end = end.bump()
            parts.extend(f"!={v}" for v in cls._populate_version_range(start, end))
        return ",".join(parts)

    def __repr__(self) -> str:
        return f"<PySpecSet {self}>"

    def __and__(self, other: Any) -> PySpecSet:
        if isinstance(other, PySpecSet):
            return type(self)(self._logic & other._logic)
        elif isinstance(other, VersionSpecifier):
            return type(self)(self._logic & other)
        return NotImplemented

    def __or__(self, other: Any) -> PySpecSet:
        if isinstance(other, PySpecSet):
            return type(self)(self._logic | other._logic)
        elif isinstance(other, VersionSpecifier):
            return type(self)(self._logic | other)
        return NotImplemented

    @classmethod
    def _populate_version_range(cls, lower: Version, upper: Version) -> Iterable[Version]:
        """Expand the version range to a collection of versions to exclude,
        taking the released python versions into consideration.
        """
        assert lower < upper
        prev = lower
        while prev < upper:
            if prev[-2:] == Version((0, 0)):  # X.0.0
                cur = prev.bump(0)  # X+1.0.0
                if cur <= upper:  # It is still within the range
                    yield Version((prev[0], "*"))  # Exclude the whole major series: X.*
                    prev = cur
                    continue
            if prev[-1] == 0:  # X.Y.0
                cur = prev.bump(1)  # X.Y+1.0
                if cur <= upper:  # It is still within the range
                    yield prev[:2].complete("*")  # Exclude X.Y.*
                    prev = (
                        prev.bump(0) if cur.is_py2 and cast(int, cur[1]) > cls.PY_MAX_MINOR_VERSION[cur[:1]] else cur
                    )  # If prev is 2.7, next is 3.0, otherwise next is X.Y+1.0
                    continue
                while prev < upper:
                    # Iterate each version from X.Y.0(prev) to X.Y.Z(upper)
                    yield prev
                    prev = prev.bump()
                break
            # Can't produce any wildcard versions
            cur = prev.bump(1)
            if cur <= upper:  # X.Y+1.0 is still within the range
                current_max = cls.PY_MAX_MINOR_VERSION[prev[:2]]
                for z in range(cast(int, prev[2]), current_max + 1):
                    yield prev[:2].complete(z)
                prev = prev.bump(0) if cur.is_py2 and cast(int, cur[1]) > cls.PY_MAX_MINOR_VERSION[cur[:1]] else cur
            else:  # Produce each version from X.Y.Z to X.Y.W
                while prev < upper:
                    yield prev
                    prev = prev.bump()
                break

    @lru_cache
    def is_superset(self, other: str | PySpecSet) -> bool:
        if self.is_empty():
            return False
        this = _fix_py4k(self._logic)
        if this.is_any():
            return True
        if isinstance(other, str):
            other = type(self)(other)
        return this & other._logic == other._logic

    @lru_cache
    def is_subset(self, other: str | PySpecSet) -> bool:
        if self.is_empty():
            return False
        if isinstance(other, str):
            other = type(self)(other)
        that = _fix_py4k(other._logic)
        if that.is_any():
            return True
        return self._logic & that == self._logic

    def as_marker_string(self) -> str:
        spec = self._logic
        if spec.is_empty():
            raise InvalidPyVersion("Impossible specifier")
        if spec.is_any():
            return ""
        return _convert_spec(cast(VersionSpecifier, spec))


def _convert_spec(specifier: VersionSpecifier) -> str:
    if isinstance(specifier, UnionSpecifier):
        return " or ".join(_convert_spec(s) for s in specifier.ranges)

    result: list[str] = []
    excludes: list[str] = []
    full_excludes: list[str] = []
    for spec in sorted(specifier.to_specifierset(), key=attrgetter("version")):
        op, version = spec.operator, spec.version
        if len(version.split(".")) < 3:
            key = "python_version"
        else:
            key = "python_full_version"
            if version[-2:] == ".*":
                version = version[:-2]
                key = "python_version"
        if op == "!=":
            if key == "python_version":
                excludes.append(version)
            else:
                full_excludes.append(version)
        else:
            result.append(f"{key}{op}{version!r}")
    if excludes:
        result.append("python_version not in {!r}".format(", ".join(sorted(excludes))))
    if full_excludes:
        result.append("python_full_version not in {!r}".format(", ".join(sorted(full_excludes))))
    return " and ".join(result)


def _fix_py4k(spec: VersionSpecifier) -> VersionSpecifier:
    """If the upper bound is 4.0, replace it with unlimited."""
    if isinstance(spec, UnionSpecifier):
        *pre, last = spec.ranges
        return UnionSpecifier([*pre, _fix_py4k(last)])
    if isinstance(spec, RangeSpecifier) and spec.max == parse_version("4.0"):
        return dataclasses.replace(spec, max=None, include_max=False)
    return spec
