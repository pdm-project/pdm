from packaging.markers import Marker as PackageMarker

from typing import Union, Optional


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
