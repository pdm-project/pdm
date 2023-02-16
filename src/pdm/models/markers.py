from __future__ import annotations

import copy
import itertools
import operator
from functools import reduce
from typing import Any

from packaging.markers import Marker as PackageMarker

from pdm.models.specifiers import PySpecSet
from pdm.utils import join_list_with


class Marker(PackageMarker):
    """A subclass of Marker that supports union and intersection merging."""

    def copy(self) -> Marker:
        inst = self.__class__('os_name == "nt"')
        inst._markers = copy.deepcopy(self._markers)
        return inst

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, PackageMarker):
            return False
        return str(self) == str(other)

    def split_pyspec(self) -> tuple[Marker | None, PySpecSet]:
        """Split `python_version` and `python_full_version` from marker string"""
        if _only_contains_python_keys(self._markers):
            return None, _build_pyspec_from_marker(self._markers)
        if "or" in self._markers:
            return self.copy(), PySpecSet()
        py_markers = [marker for marker in self._markers if marker != "and" and _only_contains_python_keys(marker)]
        rest = [marker for marker in self._markers if marker != "and" and marker not in py_markers]
        new_markers = join_list_with(rest, "and")
        if not new_markers:
            marker = None
        else:
            marker = self.copy()
            marker._markers = new_markers
        return marker, _build_pyspec_from_marker(join_list_with(py_markers, "and"))


def get_marker(marker: PackageMarker | Marker | None) -> Marker | None:
    return Marker(str(marker)) if marker else None


def split_marker_extras(marker: str) -> tuple[set[str], str]:
    """An element can be stripped from the marker only if all parts are connected
    with `and` operator. The rest part are returned as a string or `None` if all are
    stripped.
    """

    def extract_extras(submarker: tuple | list) -> set[str]:
        if isinstance(submarker, tuple):
            if submarker[0].value == "extra":
                if submarker[1].value == "==":
                    return {submarker[2].value}
                elif submarker[1].value == "in":
                    return {v.strip() for v in submarker[2].value.split(",")}
                else:
                    return set()
            else:
                return set()
        else:
            if "and" in submarker:
                return set()
            pure_extras = [extract_extras(m) for m in submarker if m != "or"]
            if all(pure_extras):
                return set(itertools.chain.from_iterable(pure_extras))
            return set()

    if not marker:
        return set(), marker
    new_marker = PackageMarker(marker)
    submarkers = PackageMarker(marker)._markers
    if "or" in submarkers:
        extras = extract_extras(submarkers)
        if extras:
            return extras, ""
        return set(), marker

    extras = set()
    submarkers_no_extras: list[tuple | list] = []
    # Below this point the submarkers are connected with 'and'
    for submarker in submarkers:
        if submarker == "and":
            continue
        new_extras = extract_extras(submarker)
        if new_extras:
            if extras:
                # extras are not allowed to appear in more than one parts
                return set(), marker
            extras.update(new_extras)
        else:
            submarkers_no_extras.append(submarker)

    if not submarkers_no_extras:
        return extras, ""
    new_marker._markers = join_list_with(submarkers_no_extras, "and")
    return extras, str(new_marker)


def _only_contains_python_keys(markers: list[Any]) -> bool:
    if isinstance(markers, tuple):
        return markers[0].value in ("python_version", "python_full_version")

    for marker in markers:
        if marker in ("and", "or"):
            continue
        if not _only_contains_python_keys(marker):
            return False
    return True


def _build_pyspec_from_marker(markers: list[Any]) -> PySpecSet:
    def split_version(version: str) -> list[str]:
        if "," in version:
            return [v.strip() for v in version.split(",")]
        return version.split()

    groups = [PySpecSet()]
    for marker in markers:
        if isinstance(marker, list):
            # It is a submarker
            groups[-1] = groups[-1] & _build_pyspec_from_marker(marker)
        elif isinstance(marker, tuple):
            key, op, version = (i.value for i in marker)
            if key == "python_version":
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
            groups[-1] = groups[-1] & pyspec
        else:
            assert marker in ("and", "or")
            if marker == "or":
                groups.append(PySpecSet())
    return reduce(operator.or_, groups)
