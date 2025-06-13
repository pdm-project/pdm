from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING, Iterable

import tomlkit

from pdm.project.lockfile.base import (
    FLAG_CROSS_PLATFORM,
    FLAG_DIRECT_MINIMAL_VERSIONS,
    FLAG_INHERIT_METADATA,
    FLAG_STATIC_URLS,
    Compatibility,
    Lockfile,
)
from pdm.utils import parse_version

if TYPE_CHECKING:
    from pdm.models.repositories import LockedRepository


class PDMLock(Lockfile):
    SUPPORTED_FLAGS = frozenset(
        (FLAG_STATIC_URLS, FLAG_CROSS_PLATFORM, FLAG_DIRECT_MINIMAL_VERSIONS, FLAG_INHERIT_METADATA)
    )
    spec_version = parse_version("4.5.0")

    @property
    def hash(self) -> tuple[str, str]:
        content_hash = self._data.get("metadata", {}).get("content_hash", "")
        return content_hash.split(":", 1)

    @property
    def file_version(self) -> str:
        return self._data.get("metadata", {}).get("lock_version", "")

    @property
    def groups(self) -> list[str] | None:
        return self._data.get("metadata", {}).get("groups")

    @cached_property
    def default_strategies(self) -> set[str]:
        return {FLAG_INHERIT_METADATA}

    @property
    def strategy(self) -> set[str]:
        metadata = self._data.get("metadata", {})
        if not metadata:
            return self.default_strategies.copy()
        result: set[str] = set(metadata.get("strategy", {FLAG_CROSS_PLATFORM}))
        # Compatibility with old lockfiles
        if not metadata.get(FLAG_CROSS_PLATFORM, True):
            result.discard(FLAG_CROSS_PLATFORM)
        if metadata.get(FLAG_STATIC_URLS, False):
            result.add(FLAG_STATIC_URLS)
        return result & self.SUPPORTED_FLAGS

    def update_hash(self, hash_value: str, algo: str = "sha256") -> None:
        self._data.setdefault("metadata", {})["content_hash"] = f"{algo}:{hash_value}"

    def compatibility(self) -> Compatibility:
        """We use a three-part versioning scheme for lockfiles:
        The first digit represents backward compatibility and the second digit represents forward compatibility.
        """
        if not self.exists():
            return Compatibility.SAME
        if not self.file_version:
            return Compatibility.NONE
        lockfile_version = parse_version(self.file_version)
        if lockfile_version == self.spec_version:
            return Compatibility.SAME
        if lockfile_version.major != self.spec_version.major or lockfile_version.minor > self.spec_version.minor:
            return Compatibility.NONE
        if lockfile_version.minor < self.spec_version.minor:
            return Compatibility.BACKWARD
        return Compatibility.BACKWARD if lockfile_version.micro < self.spec_version.micro else Compatibility.FORWARD

    def format_lockfile(self, repository: LockedRepository, groups: Iterable[str] | None, strategy: set[str]) -> None:
        """Format lock file from a dict of resolved candidates, a mapping of dependencies
        and a collection of package summaries.
        """
        from pdm.formats.base import make_array, make_inline_table

        def _group_sort_key(group: str) -> tuple[bool, str]:
            return group != "default", group

        project = repository.environment.project
        packages = tomlkit.aot()
        for entry in sorted(repository.packages.values(), key=lambda x: x.candidate.identify()):
            base = tomlkit.table()
            base.update(entry.candidate.as_lockfile_entry(project.root))
            base.add("summary", entry.summary or "")
            if FLAG_INHERIT_METADATA in strategy:
                base.add("groups", sorted(entry.candidate.req.groups, key=_group_sort_key))
                if entry.candidate.req.marker is not None:
                    base.add("marker", str(entry.candidate.req.marker))
            if entry.dependencies:
                base.add("dependencies", make_array(sorted(entry.dependencies), True))
            if hashes := entry.candidate.hashes:
                collected = {}
                for item in hashes:
                    if FLAG_STATIC_URLS in strategy:
                        row = {"url": item["url"], "hash": item["hash"]}
                    else:
                        row = {"file": item["file"], "hash": item["hash"]}
                    inline = make_inline_table(row)
                    # deduplicate and sort
                    collected[tuple(row.values())] = inline
                if collected:
                    base.add("files", make_array([collected[k] for k in sorted(collected)], True))
            packages.append(base)
        doc = tomlkit.document()
        metadata = tomlkit.table()
        if groups is None:
            groups = list(project.iter_groups())
        metadata.update(
            {
                "groups": sorted(groups, key=_group_sort_key),
                "strategy": sorted(strategy),
                "targets": [t.as_dict() for t in repository.targets],
                "lock_version": str(self.spec_version),
            }
        )
        metadata.pop(FLAG_STATIC_URLS, None)
        metadata.pop(FLAG_CROSS_PLATFORM, None)
        doc.add("metadata", metadata)
        doc.add("package", packages)
        self.set_data(doc)
