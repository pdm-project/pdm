from packaging.markers import Marker as PackageMarker

from typing import Union, Optional, Tuple, Iterable


class Marker(PackageMarker):
    def __and__(self, other: Optional[PackageMarker]) -> "Marker":
        if other is None:
            return self
        lhs = f"({self})" if "or" in self._markers else str(self)
        rhs = f"({other})" if "or" in other._markers else str(other)
        marker_str = f"{lhs} and {rhs}"
        return type(self)(marker_str)

    def __rand__(self, other: Optional[PackageMarker]) -> "Marker":
        if other is None:
            return self
        rhs = f"({self})" if "or" in self._markers else str(self)
        lhs = f"({other})" if "or" in other._markers else str(other)
        marker_str = f"{lhs} and {rhs}"
        return type(self)(marker_str)

    def __or__(self, other: Optional[PackageMarker]) -> "Marker":
        if other is None:
            return self
        marker_str = f"{self} or {other}"
        return type(self)(marker_str)

    def __ror__(self, other: Optional[PackageMarker]) -> "Marker":
        if other is None:
            return self
        marker_str = f"{other} or {self}"
        return type(self)(marker_str)


def get_marker(marker: Union[PackageMarker, Marker, None]) -> Optional[Marker]:
    return Marker(str(marker)) if marker else None


def split_marker_element(
    text: str, element: str
) -> Tuple[Iterable[Tuple[str, str]], Optional[str]]:
    """An element can be stripped from the marker only if all parts are connected
    with `and` operater. The rest part are returned as a string or `None` if all are
    stripped.

    :param text: the input marker string
    :param element: the element to be stripped
    :returns: an iterable of (op, value) pairs together with the stripped part.
    """
    if not text:
        return [], text
    marker = Marker(text)
    if "or" in marker._markers:
        return [], text
    result = []
    bare_markers = [m for m in marker._markers if m != "and"]
    for m in bare_markers[:]:
        if not isinstance(m, tuple):
            continue
        if m[0].value == element:
            result.append(tuple(e.value for e in m[1:]))
            bare_markers.remove(m)
    if not bare_markers:
        return result, None
    new_markers = [bare_markers[0]]
    for m in bare_markers[1:]:
        new_markers.extend(["and", m])
    marker._markers = new_markers
    return result, marker
