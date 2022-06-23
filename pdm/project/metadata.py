import os
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any, Dict, Iterator, List, TypeVar, Union

from pdm.compat import tomllib
from pdm.formats import flit, poetry
from pdm.pep517.metadata import Metadata

T = TypeVar("T")


class MutableMetadata(Metadata, MutableMapping):
    """
    A subclass of Metadata that delegates some modifying methods
    to the underlying toml parsed dict.
    """

    def __init__(self, root: Union[str, Path], pyproject: Dict[str, Any]) -> None:
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
    def from_file(cls, filename: Union[str, Path]) -> "MutableMetadata":
        """Get the metadata from a pyproject.toml file"""
        return cls(os.path.dirname(filename), tomllib.load(open(filename, "rb")))

    def __getitem__(self, k: str) -> Union[Dict, List[str], str]:
        return self.data[k]

    def __setitem__(self, k: str, v: Union[Dict, List[str], str]) -> None:
        self.data[k] = v

    def __delitem__(self, k: str) -> None:
        del self.data[k]

    def __iter__(self) -> Iterator:
        return iter(self.data)

    def __len__(self) -> int:
        return len(self.data)

    def setdefault(self, key: str, default: T) -> T:  # type: ignore
        return self.data.setdefault(key, default)
