from __future__ import annotations

import os
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any, Iterator, TypeVar

from pdm.compat import Distribution, tomllib
from pdm.models.markers import Marker
from pdm.models.requirements import parse_requirement
from pdm.models.setup import Setup
from pdm.pep517.metadata import Metadata

T = TypeVar("T")


class MutableMetadata(Metadata, MutableMapping):
    """
    A subclass of Metadata that delegates some modifying methods
    to the underlying toml parsed dict.
    """

    def __init__(self, root: str | Path, pyproject: dict[str, Any]) -> None:
        from pdm.formats import flit, poetry

        try:
            super().__init__(root, pyproject)
        except ValueError as e:
            for converter in (flit, poetry):
                filename = os.path.join(root, "pyproject.toml")
                if converter.check_fingerprint(None, filename):
                    data, settings = converter.convert(None, filename, None)
                    pyproject.setdefault("project", {}).update(data)
                    pyproject.setdefault("tool", {}).setdefault("pdm", {}).update(
                        settings
                    )
                    return super().__init__(root, pyproject)
            raise e from None

    @classmethod
    def from_file(cls, filename: str | Path) -> MutableMetadata:
        """Get the metadata from a pyproject.toml file"""
        return cls(os.path.dirname(filename), tomllib.load(open(filename, "rb")))

    def __getitem__(self, k: str) -> dict | list[str] | str:
        return self.data[k]

    def __setitem__(self, k: str, v: dict | list[str] | str) -> None:
        self.data[k] = v

    def __delitem__(self, k: str) -> None:
        del self.data[k]

    def __iter__(self) -> Iterator:
        return iter(self.data)

    def __len__(self) -> int:
        return len(self.data)

    def setdefault(self, key: str, default: T) -> T:  # type: ignore
        return self.data.setdefault(key, default)


class SetupDistribution(Distribution):
    def __init__(self, data: Setup) -> None:
        self._data = data

    def read_text(self, filename: str) -> str | None:
        return None

    def locate_file(self, path: os.PathLike[str] | str) -> os.PathLike[str]:
        return Path("")

    @property
    def metadata(self) -> dict[str, Any]:  # type: ignore
        return {
            "Name": self._data.name,
            "Version": self._data.version,
            "Summary": "UNKNOWN",
            "Requires-Python": self._data.python_requires,
        }

    @property
    def requires(self) -> list[str] | None:
        result = self._data.install_requires
        for extra, reqs in self._data.extras_require.items():
            extra_marker = f"extra == '{extra}'"
            for req in reqs:
                parsed = parse_requirement(req)
                old_marker = str(parsed.marker) if parsed.marker else None
                if old_marker:
                    if " or " in old_marker:
                        new_marker = f"({old_marker}) and {extra_marker}"
                    else:
                        new_marker = f"{old_marker} and {extra_marker}"
                else:
                    new_marker = extra_marker
                parsed.marker = Marker(new_marker)
                result.append(parsed.as_line())
        return result
