from collections.abc import MutableMapping

from pdm.pep517.metadata import Metadata


class MutableMetadata(Metadata, MutableMapping):
    """
    A subclass of Metadata that delegates some modifying methods
    to the underlying toml parsed dict.
    """

    def __init__(self, filepath, data=None) -> None:
        self.filepath = filepath
        if data is None:
            data = self._read_pyproject(filepath)
        self._metadata = data

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
