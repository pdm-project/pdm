from __future__ import annotations

import operator
from dataclasses import dataclass
from functools import reduce
from typing import Any, overload

from dep_logic.markers import (
    BaseMarker,
    InvalidMarker,
    MarkerExpression,
    MarkerUnion,
    MultiMarker,
    from_pkg_marker,
    parse_marker,
)
from packaging.markers import Marker as PackageMarker

from pdm.exceptions import RequirementError
from pdm.models.specifiers import PySpecSet


@dataclass(frozen=True, unsafe_hash=True, repr=False)
class Marker:
    inner: BaseMarker

    def __and__(self, other: Any) -> Marker:
        if not isinstance(other, Marker):
            return NotImplemented
        return type(self)(self.inner & other.inner)

    def __or__(self, other: Any) -> Marker:
        if not isinstance(other, Marker):
            return NotImplemented
        return type(self)(self.inner | other.inner)

    def is_any(self) -> bool:
        return self.inner.is_any()

    def is_empty(self) -> bool:
        return self.inner.is_empty()

    def __str__(self) -> str:
        return str(self.inner)

    def __repr__(self) -> str:
        return f"<Marker {self.inner}>"

    def evaluate(self, environment: dict[str, Any] | None = None) -> bool:
        return self.inner.evaluate(environment)

    def split_pyspec(self) -> tuple[Marker, PySpecSet]:
        """Split `python_version` and `python_full_version` from marker string"""
        python_marker = self.inner.only("python_version", "python_full_version")
        if python_marker.is_any():
            return self, PySpecSet()
        new_marker = type(self)(self.inner.exclude("python_version").exclude("python_full_version"))
        return new_marker, _build_pyspec_from_marker(python_marker)

    def split_extras(self) -> tuple[Marker, Marker]:
        """An element can be stripped from the marker only if all parts are connected
        with `and` operator. The rest part are returned as a string or `None` if all are
        stripped.
        """
        return type(self)(self.inner.without_extras()), type(self)(self.inner.only("extra"))


@overload
def get_marker(marker: None) -> None:
    ...


@overload
def get_marker(marker: PackageMarker | Marker | str) -> Marker:
    ...


def get_marker(marker: PackageMarker | Marker | str | None) -> Marker | None:
    if marker is None:
        return None
    if isinstance(marker, Marker):
        return marker
    elif isinstance(marker, PackageMarker):
        return Marker(from_pkg_marker(marker))
    try:
        return Marker(parse_marker(marker))
    except InvalidMarker as e:
        raise RequirementError(f"Invalid marker {marker}: {e}") from e


def _build_pyspec_from_marker(marker: BaseMarker) -> PySpecSet:
    def split_version(version: str) -> list[str]:
        if "," in version:
            return [v.strip() for v in version.split(",")]
        return version.split()

    if isinstance(marker, MarkerExpression):
        name = marker.name
        op = marker.op
        version = marker.value
        if name == "python_version":
            if op == ">":
                int_versions = [int(ver) for ver in version.split(".")]
                if len(int_versions) < 2:
                    int_versions.append(0)
                int_versions[-1] += 1
                version = ".".join(str(v) for v in int_versions)
                op = ">="
            elif op in ("==", "!="):
                if len(version.split(".")) < 3:
                    version += ".*"
            elif op in ("in", "not in"):
                version = " ".join(v + ".*" for v in split_version(version))
        if op == "in":
            pyspec = reduce(operator.or_, (PySpecSet(f"=={v}") for v in split_version(version)))
        elif op == "not in":
            pyspec = reduce(operator.and_, (PySpecSet(f"!={v}") for v in split_version(version)))
        else:
            pyspec = PySpecSet(f"{op}{version}")
        return pyspec
    elif isinstance(marker, MultiMarker):
        return reduce(operator.and_, (_build_pyspec_from_marker(m) for m in marker.markers))
    elif isinstance(marker, MarkerUnion):
        return reduce(operator.or_, (_build_pyspec_from_marker(m) for m in marker.markers))
    else:  # pragma: no cover
        raise TypeError(f"Unsupported marker type: {type(marker)}")
