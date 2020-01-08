import json
from pathlib import Path
from typing import Dict, Any


class _JSONCache:
    def __init__(self, cache_file: Path) -> None:
        self.cache_file = cache_file
        self._cache = {}  # type: Dict[str, Any]
        self._read_cache()

    def _read_cache(self) -> None:
        with self.cache_file.open() as fp:
            self._cache = json.load(fp)

    def get(self, key: str) -> Any:
        return self._cache[key]
