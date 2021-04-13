from collections.abc import MutableMapping
from typing import Dict, Iterator, List, Union

from pdm.formats import flit, poetry
from pdm.pep517.metadata import Metadata


class MutableMetadata(Metadata, MutableMapping):
    """
    A subclass of Metadata that delegates some modifying methods
    to the underlying toml parsed dict.
    """

    def _read_pyproject(self) -> None:
        try:
            return super()._read_pyproject()
        except ValueError:
            for converter in (poetry, flit):
                if converter.check_fingerprint(None, self.filepath):
                    data, settings = converter.convert(None, self.filepath, None)
                    self._metadata = dict(data)
                    self._tool_settings = settings
                    return
            raise

    def __getitem__(self, k: str) -> Union[Dict, List[str], str]:
        return self._metadata[k]

    def __setitem__(self, k: str, v: Union[Dict, List[str], str]) -> None:
        self._metadata[k] = v

    def __delitem__(self, k: str) -> None:
        del self._metadata[k]

    def __iter__(self) -> Iterator:
        return iter(self._metadata)

    def __len__(self) -> int:
        return len(self._metadata)
