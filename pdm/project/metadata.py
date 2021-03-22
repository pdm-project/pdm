from collections.abc import MutableMapping
from pathlib import Path

from pdm.formats import flit, poetry
from pdm.pep517.metadata import Metadata


class MutableMetadata(Metadata, MutableMapping):
    """
    A subclass of Metadata that delegates some modifying methods
    to the underlying toml parsed dict.
    """

    def __init__(self, filepath, data=None) -> None:
        self.filepath = Path(filepath)
        if data is None:
            data = self._read_pyproject(self.filepath)
        self._metadata = data

    @staticmethod
    def _read_pyproject(filepath):
        try:
            return Metadata._read_pyproject(filepath)
        except ValueError:
            for converter in (poetry, flit):
                if converter.check_fingerprint(None, filepath):
                    data, _ = converter.convert(None, filepath, None)
                    return data
            raise

    def __getitem__(self, k):
        return self._metadata[k]

    def __setitem__(self, k, v):
        self._metadata[k] = v

    def __delitem__(self, k):
        del self._metadata[k]

    def __iter__(self):
        return iter(self._metadata)

    def __len__(self):
        return len(self._metadata)
