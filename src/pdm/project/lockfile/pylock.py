from __future__ import annotations

from functools import cached_property
from typing import Iterable

from pdm.exceptions import PdmUsageError
from pdm.models.repositories.lock import LockedRepository
from pdm.project.lockfile.base import (
    FLAG_DIRECT_MINIMAL_VERSIONS,
    FLAG_INHERIT_METADATA,
    FLAG_STATIC_URLS,
    Compatibility,
    Lockfile,
)


class PyLock(Lockfile):
    SUPPORTED_FLAGS = frozenset([FLAG_DIRECT_MINIMAL_VERSIONS, FLAG_INHERIT_METADATA, FLAG_STATIC_URLS])

    @property
    def hash(self) -> tuple[str, str]:
        return next(iter(self._data.get("tool", {}).get("pdm", {}).get("hashes", {}).items()), ("", ""))

    def update_hash(self, hash_value: str, algo: str = "sha256") -> None:
        self._data.setdefault("tool", {}).setdefault("pdm", {}).setdefault("hashes", {})[algo] = hash_value

    @property
    def groups(self) -> list[str] | None:
        return [*self._data.get("dependency-groups", []), *self._data.get("extras", [])]

    @cached_property
    def default_strategies(self) -> set[str]:
        return {FLAG_INHERIT_METADATA, FLAG_STATIC_URLS}

    @property
    def strategy(self) -> set[str]:
        return set(self._data.get("tool", {}).get("pdm", {}).get("strategy", self.default_strategies))

    def apply_strategy_change(self, changes: Iterable[str]) -> set[str]:
        for change in changes:
            change = change.replace("-", "_").lower()
            if change.startswith("no_") and change[3:] != FLAG_DIRECT_MINIMAL_VERSIONS:
                raise PdmUsageError(f"Unsupported strategy change for pylock: {change}")
        return super().apply_strategy_change(changes)

    def format_lockfile(self, repository: LockedRepository, groups: Iterable[str] | None, strategy: set[str]) -> None:
        from pdm.formats.pylock import PyLockConverter

        converter = PyLockConverter(repository.environment.project, repository)
        data = converter.convert(groups)
        data["tool"]["pdm"]["strategy"] = sorted(strategy)
        self.set_data(data)

    def compatibility(self) -> Compatibility:  # pragma: no cover
        return Compatibility.SAME
