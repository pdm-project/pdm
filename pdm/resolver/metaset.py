from typing import Optional

from pdm.models.markers import Marker
from pdm.models.specifiers import PySpecSet


class Metaset:
    """A wrapper class on top of :class:`pdm.models.markers.Marker`
    with the ability to merge python specifiers
    """

    def __init__(self, marker: Optional[Marker] = None) -> None:
        if not marker:
            self.marker_no_python, self.requires_python = None, PySpecSet()
        else:
            self.marker_no_python, self.requires_python = marker.split_pyspec()

    def __and__(self, other: "Metaset") -> "Metaset":
        if not isinstance(other, Metaset):
            raise TypeError(f"Can't perform 'and' with type {type(other)} object")
        inst = Metaset()
        inst.marker_no_python = (
            self.marker_no_python & other.marker_no_python
            if any([self.marker_no_python, other.marker_no_python])
            else None
        )
        inst.requires_python = self.requires_python & other.requires_python
        return inst

    def __or__(self, other: "Metaset") -> "Metaset":
        if not isinstance(other, Metaset):
            raise TypeError(f"Can't perform 'or' with type {type(other)} object")
        inst = Metaset()
        inst.marker_no_python = (
            self.marker_no_python | other.marker_no_python
            if any([self.marker_no_python, other.marker_no_python])
            else None
        )
        inst.requires_python = self.requires_python | other.requires_python
        return inst

    def as_marker(self) -> Optional[Marker]:
        marker, pyspec = self.marker_no_python, self.requires_python
        py_marker = pyspec.as_marker_string() or None
        py_marker = Marker(py_marker) if py_marker else None
        try:
            return marker & py_marker
        except TypeError:
            return None
