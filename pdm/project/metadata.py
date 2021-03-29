from collections.abc import MutableMapping

from pdm.formats import flit, poetry
from pdm.pep517.metadata import Metadata


class MutableMetadata(Metadata, MutableMapping):
    """
    A subclass of Metadata that delegates some modifying methods
    to the underlying toml parsed dict.
    """

    def _read_pyproject(self):
        try:
            return super()._read_pyproject()
        except ValueError:
            for converter in (poetry, flit):
                if converter.check_fingerprint(None, self.filepath):
                    data, settings = converter.convert(None, self.filepath, None)
                    self._metadata = data
                    self._tool_settings = settings
                    return
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
