import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from pdm._types import CandidateInfo
from pdm.exceptions import CorruptedCacheError
from pdm.models import pip_shims
from pdm.models.candidates import Candidate
from pdm.utils import open_file

if TYPE_CHECKING:
    from pip._vendor import requests


class CandidateInfoCache:
    """Cache manager to hold (dependencies, requires_python, summary) info."""

    def __init__(self, cache_file: Path) -> None:
        self.cache_file = cache_file
        self._cache: Dict[str, CandidateInfo] = {}
        self._read_cache()

    def _read_cache(self) -> None:
        if not self.cache_file.exists():
            self._cache = {}
            return
        with self.cache_file.open() as fp:
            try:
                self._cache = json.load(fp)
            except json.JSONDecodeError:
                raise CorruptedCacheError("The dependencies cache seems to be broken.")

    def _write_cache(self) -> None:
        with self.cache_file.open("w") as fp:
            json.dump(self._cache, fp)

    @staticmethod
    def _get_key(candidate: Candidate) -> str:
        # Name and version are set when dependencies are resolved,
        # so use them for cache key. Local directories won't be cached.
        if not candidate.name or not candidate.version:
            raise KeyError
        extras = (
            "[{}]".format(",".join(sorted(candidate.req.extras)))
            if candidate.req.extras
            else ""
        )
        return f"{candidate.name}{extras}-{candidate.version}"

    def get(self, candidate: Candidate) -> CandidateInfo:
        key = self._get_key(candidate)
        return self._cache[key]

    def set(self, candidate: Candidate, value: CandidateInfo) -> None:
        key = self._get_key(candidate)
        self._cache[key] = value
        self._write_cache()

    def delete(self, candidate: Candidate) -> None:
        try:
            del self._cache[self._get_key(candidate)]
        except KeyError:
            pass
        self._write_cache()

    def clear(self) -> None:
        self._cache.clear()
        self._write_cache()


class HashCache(pip_shims.SafeFileCache):

    """Caches hashes of PyPI artifacts so we do not need to re-download them.

    Hashes are only cached when the URL appears to contain a hash in it and the
    cache key includes the hash value returned from the server). This ought to
    avoid issues where the location on the server changes.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.session: Optional[requests.Session] = None
        super(HashCache, self).__init__(*args, **kwargs)

    def get_hash(self, link: pip_shims.Link) -> str:
        # If there is no link hash (i.e., md5, sha256, etc.), we don't want
        # to store it.
        hash_value = self.get(link.url)
        if not hash_value:
            if link.hash and link.hash_name in pip_shims.STRONG_HASHES:
                hash_value = f"{link.hash_name}:{link.hash}"
            else:
                hash_value = self._get_file_hash(link)
            hash_value = hash_value.encode()
            self.set(link.url, hash_value)
        return hash_value.decode("utf8")

    def _get_file_hash(self, link: pip_shims.Link) -> str:
        h = hashlib.new(pip_shims.FAVORITE_HASH)
        with open_file(link.url, self.session) as fp:
            for chunk in iter(lambda: fp.read(8096), b""):
                h.update(chunk)
        return ":".join([h.name, h.hexdigest()])
