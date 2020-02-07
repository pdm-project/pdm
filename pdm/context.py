from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

from pip_shims import shims

from pdm import __version__
from pdm.ui import _IO

if TYPE_CHECKING:
    from pdm.models.caches import CandidateInfoCache, HashCache


class Context:
    """A singleton context object that holds some global states.
    Global states are evil but make it easier to share configs between
    different modules.
    """

    def __init__(self):
        self.version = __version__
        self.project = None
        self.io = _IO()

    def init(self, project):
        self.project = project

    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    def cache_dir(self) -> Path:
        return Path(self.project.config.get("cache_dir"))

    def cache(self, name: str) -> Path:
        path = self.cache_dir / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def make_wheel_cache(self) -> shims.WheelCache:
        return shims.WheelCache(
            self.cache_dir.as_posix(), shims.FormatControl(set(), set())
        )

    def make_candidate_info_cache(self) -> CandidateInfoCache:
        from pdm.models.caches import CandidateInfoCache

        python_hash = hashlib.sha1(
            str(self.project.python_requires).encode()
        ).hexdigest()
        file_name = f"package_meta_{python_hash}.json"
        return CandidateInfoCache(self.cache_dir / file_name)

    def make_hash_cache(self) -> HashCache:
        from pdm.models.caches import HashCache

        return HashCache(directory=self.cache("hashes").as_posix())


context = Context()
