from __future__ import annotations

from collections.abc import Iterable
from functools import cached_property

from pdm.exceptions import PdmUsageError
from pdm.models.repositories.lock import LockedRepository
from pdm.project.lockfile.base import (
    FLAG_DIRECT_MINIMAL_VERSIONS,
    FLAG_INHERIT_METADATA,
    FLAG_STATIC_URLS,
    Compatibility,
    Lockfile,
    LockInputsState,
)


class PyLock(Lockfile):
    SUPPORTED_FLAGS = frozenset([FLAG_DIRECT_MINIMAL_VERSIONS, FLAG_INHERIT_METADATA, FLAG_STATIC_URLS])

    @property
    def hash(self) -> tuple[str, str]:
        return next(iter(self._data.get("tool", {}).get("pdm", {}).get("hashes", {}).items()), ("", ""))

    def update_hash(self, hash_value: str, algo: str = "sha256") -> None:
        self._data.setdefault("tool", {}).setdefault("pdm", {}).setdefault("hashes", {})[algo] = hash_value

    @property
    def lock_inputs(self) -> object | None:
        return self._data.get("tool", {}).get("pdm", {}).get("lock_inputs")

    @property
    def lock_inputs_state(self) -> LockInputsState:
        metadata = self._data.get("tool", {}).get("pdm", {})
        if "lock_inputs" not in metadata:
            return LockInputsState.LEGACY
        return LockInputsState.SUPPORTED if self.lock_inputs is not None else LockInputsState.INVALID

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
        if repository.environment.project.lock_inputs_enabled():
            data["tool"]["pdm"].pop("hashes", None)
            data["tool"]["pdm"]["lock_inputs"] = repository.environment.project.lock_inputs()
        self.set_data(data)

    def compatibility(self) -> Compatibility:  # pragma: no cover
        return Compatibility.SAME
