from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import json
import os
import stat
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Generic, Iterable, TypeVar

import httpx
from packaging.utils import canonicalize_name, parse_wheel_filename

from pdm._types import CandidateInfo
from pdm.exceptions import PdmException
from pdm.models.cached_package import CachedPackage
from pdm.models.candidates import Candidate
from pdm.termui import logger
from pdm.utils import atomic_open_for_write, create_tracked_tempdir, get_file_hash

if TYPE_CHECKING:
    from packaging.tags import Tag
    from unearth import Link, TargetPython

    from pdm.environments import BaseEnvironment

KT = TypeVar("KT")
VT = TypeVar("VT")


class JSONFileCache(Generic[KT, VT]):
    """A file cache that stores key-value pairs in a json file."""

    def __init__(self, cache_file: Path | str) -> None:
        self.cache_file = Path(cache_file)
        self._cache: dict[str, VT] = {}
        self._read_cache()

    def _read_cache(self) -> None:
        if not self.cache_file.exists():
            self._cache = {}
            return
        with self.cache_file.open() as fp:
            try:
                self._cache = json.load(fp)
            except json.JSONDecodeError:
                return

    def _write_cache(self) -> None:
        with self.cache_file.open("w") as fp:
            json.dump(self._cache, fp)

    def __contains__(self, obj: KT) -> bool:
        return self._get_key(obj) in self._cache

    @classmethod
    def _get_key(cls, obj: KT) -> str:
        return str(obj)

    def get(self, obj: KT) -> VT:
        key = self._get_key(obj)
        return self._cache[key]

    def set(self, obj: KT, value: VT) -> None:
        key = self._get_key(obj)
        self._cache[key] = value
        self._write_cache()

    def delete(self, obj: KT) -> None:
        try:
            del self._cache[self._get_key(obj)]
        except KeyError:
            pass
        self._write_cache()

    def clear(self) -> None:
        self._cache.clear()
        self._write_cache()


class CandidateInfoCache(JSONFileCache[Candidate, CandidateInfo]):
    """A cache manager that stores the
    candidate -> (dependencies, requires_python, summary) mapping.
    """

    @staticmethod
    def get_url_part(link: Link) -> str:
        import base64

        from pdm.utils import url_without_fragments

        url = url_without_fragments(link.split_auth()[1])
        return base64.urlsafe_b64encode(url.encode()).decode()

    @classmethod
    def _get_key(cls, obj: Candidate) -> str:
        # Name and version are set when dependencies are resolved,
        # so use them for cache key. Local directories won't be cached.
        if not obj.name or not obj.version:
            raise KeyError("The package is missing a name or version")
        extras = "[{}]".format(",".join(sorted(obj.req.extras))) if obj.req.extras else ""
        version = obj.version
        if not obj.req.is_named:
            assert obj.link is not None
            version = cls.get_url_part(obj.link)
        return f"{obj.name}{extras}-{version}"


class HashCache:
    """Caches hashes of PyPI artifacts so we do not need to re-download them.

    Hashes are only cached when the URL appears to contain a hash in it and the
    cache key includes the hash value returned from the server). This ought to
    avoid issues where the location on the server changes.
    """

    FAVORITE_HASH = "sha256"
    STRONG_HASHES = ("sha256", "sha384", "sha512")

    def __init__(self, directory: Path | str) -> None:
        self.directory = Path(directory)

    def _read_from_link(self, link: Link, session: httpx.Client) -> Iterable[bytes]:
        if link.is_file:
            with open(link.file_path, "rb") as f:
                yield from f
        else:
            import httpx

            with session.stream("GET", link.normalized) as resp:
                try:
                    resp.raise_for_status()
                except httpx.HTTPStatusError as e:
                    raise PdmException(f"Failed to read from {link.redacted}: {e}") from e
                yield from resp.iter_bytes(chunk_size=8192)

    def _get_file_hash(self, link: Link, session: httpx.Client) -> str:
        h = hashlib.new(self.FAVORITE_HASH)
        logger.debug("Downloading link %s for calculating hash", link.redacted)
        for chunk in self._read_from_link(link, session):
            h.update(chunk)
        return ":".join([h.name, h.hexdigest()])

    def _should_cache(self, link: Link) -> bool:
        # For now, we only disable caching for local files.
        # We may add more when we know better about it.
        return not link.is_file

    def get_hash(self, link: Link, session: httpx.Client) -> str:
        # If there is no link hash (i.e., md5, sha256, etc.), we don't want
        # to store it.
        hash_value = self.get(link.url_without_fragment)
        if not hash_value:
            if link.hashes and link.hashes.keys() & self.STRONG_HASHES:
                logger.debug("Using hash in link for %s", link.redacted)
                hash_name = next(k for k in self.STRONG_HASHES if k in link.hashes)
                hash_value = f"{hash_name}:{link.hashes[hash_name]}"
            elif link.hash and link.hash_name in self.STRONG_HASHES:
                logger.debug("Using hash in link for %s", link.redacted)
                hash_value = f"{link.hash_name}:{link.hash}"
            else:
                hash_value = self._get_file_hash(link, session)
            if self._should_cache(link):
                self.set(link.url_without_fragment, hash_value)
        return hash_value

    def _get_path_for_key(self, key: str) -> Path:
        hashed = hashlib.sha224(key.encode("utf-8")).hexdigest()
        parts = (hashed[:2], hashed[2:4], hashed[4:6], hashed[6:8], hashed[8:])
        return self.directory.joinpath(*parts)

    def get(self, url: str) -> str | None:
        path = self._get_path_for_key(url)
        with contextlib.suppress(OSError, UnicodeError):
            return path.read_text("utf-8").strip()
        return None

    def set(self, url: str, hash: str) -> None:
        path = self._get_path_for_key(url)
        with contextlib.suppress(OSError, UnicodeError):
            path.parent.mkdir(parents=True, exist_ok=True)
            with atomic_open_for_write(path, encoding="utf-8") as fp:
                fp.write(hash)


class WheelCache:
    """Caches wheels so we do not need to rebuild them.

    Wheels are only cached when the URL contains egg-info or is a VCS repository
    with an *immutable* revision. There might be more than one wheels built for
    one sdist, the one with most preferred tag will be returned.
    """

    def __init__(self, directory: Path | str) -> None:
        self.directory = Path(directory)
        self.ephemeral_directory = Path(create_tracked_tempdir(prefix="pdm-wheel-cache-"))

    def _get_candidates(self, path: Path) -> Iterable[Path]:
        if not path.exists():
            return
        for candidate in path.iterdir():
            if candidate.name.endswith(".whl"):
                yield candidate

    def _get_path_parts(self, link: Link, target_python: TargetPython) -> tuple[str, ...]:
        hash_key = {
            "url": link.url_without_fragment,
            # target python participates in the hash key to handle the some cases
            # where the sdist produces different wheels on different Pythons, and
            # the differences are not encoded in compatibility tags.
            "target_python": dataclasses.astuple(target_python),
        }
        if link.subdirectory:
            hash_key["subdirectory"] = link.subdirectory
        if link.hash:
            hash_key[link.hash_name] = link.hash
        hashed = hashlib.sha224(
            json.dumps(hash_key, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        ).hexdigest()
        return (hashed[:2], hashed[2:4], hashed[4:6], hashed[6:])

    def get_path_for_link(self, link: Link, target_python: TargetPython) -> Path:
        parts = self._get_path_parts(link, target_python)
        return self.directory.joinpath(*parts)

    def get_ephemeral_path_for_link(self, link: Link, target_python: TargetPython) -> Path:
        parts = self._get_path_parts(link, target_python)
        return self.ephemeral_directory.joinpath(*parts)

    def get(self, link: Link, project_name: str | None, target_python: TargetPython) -> Path | None:
        if not project_name:
            return None
        canonical_name = canonicalize_name(project_name)
        tags_priorities = {tag: i for i, tag in enumerate(target_python.supported_tags())}

        candidate = self._get_from_path(self.get_path_for_link(link, target_python), canonical_name, tags_priorities)
        if candidate is not None:
            return candidate
        return self._get_from_path(
            self.get_ephemeral_path_for_link(link, target_python), canonical_name, tags_priorities
        )

    def _get_from_path(self, path: Path, canonical_name: str, tags_priorities: dict[Tag, int]) -> Path | None:
        candidates: list[tuple[int, Path]] = []
        for candidate in self._get_candidates(path):
            try:
                name, *_, tags = parse_wheel_filename(candidate.name)
            except ValueError:
                logger.debug("Ignoring invalid cached wheel %s", candidate.name)
                continue
            if canonical_name != canonicalize_name(name):
                logger.debug(
                    "Ignoring cached wheel %s with invalid project name %s, expected: %s",
                    candidate.name,
                    name,
                    canonical_name,
                )
                continue
            if tags.isdisjoint(tags_priorities):
                continue
            support_min = min(tags_priorities[tag] for tag in tags if tag in tags_priorities)
            candidates.append((support_min, candidate))
        if not candidates:
            return None
        return min(candidates, key=lambda x: x[0])[1]


@lru_cache(maxsize=None)
def get_wheel_cache(directory: Path | str) -> WheelCache:
    return WheelCache(directory)


class PackageCache:
    def __init__(self, root: Path) -> None:
        self.root = root

    def cache_wheel(self, wheel: Path, environment: BaseEnvironment, checksum: str | None = None) -> CachedPackage:
        """Create a CachedPackage instance from a wheel file"""
        import zipfile

        from installer.utils import make_file_executable

        if checksum is None:
            checksum = get_file_hash(wheel)
        parts = (checksum[:2], checksum[2:4], checksum[4:6], checksum[6:8], checksum[8:])
        dest = self.root.joinpath(*parts, f"{wheel.name}.cache")
        pkg = CachedPackage(dest)
        if dest.exists():
            return pkg
        dest.mkdir(parents=True, exist_ok=True)
        logger.info("Unpacking wheel into cached location %s", dest)
        with zipfile.ZipFile(wheel) as zf:
            for item in zf.infolist():
                target_path = zf.extract(item, dest)
                mode = item.external_attr >> 16
                is_executable = bool(mode and stat.S_ISREG(mode) and mode & 0o111)
                if is_executable:
                    make_file_executable(target_path)
        return pkg

    def iter_packages(self) -> Iterable[tuple[str, CachedPackage]]:
        for path in self.root.rglob("*.cache"):
            hash_parts = path.relative_to(self.root).parent.parts
            yield "".join(hash_parts), CachedPackage(path)

    def cleanup(self) -> int:
        """Remove unused cached packages"""
        count = 0
        for _, pkg in self.iter_packages():
            if not any(os.path.exists(fn) for fn in pkg.referrers):
                pkg.cleanup()
                count += 1
        return count

    def match_link(self, link: Link) -> CachedPackage | None:
        """Match a link to a cached package"""
        if not link.is_wheel:
            return None
        given_hash = link_hashes.get("sha256", []) if (link_hashes := link.hash_option) else []
        for checksum, p in self.iter_packages():
            if p.path.stem == link.filename and (not given_hash or checksum in given_hash):
                logger.debug("Using package from cache location: %s", p.path)
                return p
        return None
