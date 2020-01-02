from packaging.markers import Marker as PackageMarker

from typing import Union, Optional


class Marker(PackageMarker):
    pass


def get_marker(marker: Union[PackageMarker, Marker, None]) -> Optional[Marker]:
    return Marker(str(marker)) if marker else None
