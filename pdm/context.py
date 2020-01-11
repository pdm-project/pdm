import hashlib

from functools import wraps
from pathlib import Path

from pdm.exceptions import ProjectNotInitialized
from pdm.models.caches import CandidateInfoCache
from pdm.models.caches import HashCache
from pip_shims import shims


def require_initialize(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self.initialized:
            raise ProjectNotInitialized()
        return func(self, *args, **kwargs)

    return wrapper


class Context:
    """A singleton context object that holds some global states.
    Global states are evil but make it easier to share configs between
    different modules.
    """

    def __init__(self):
        self.project = None
        self._initialized = False

    def init(self, project):
        self.project = project
        self._initialized = True

    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    @require_initialize
    def cache_dir(self) -> Path:
        return Path(self.project.config.get("cache_dir"))

    @require_initialize
    def cache(self, name: str) -> Path:
        path = self.cache_dir / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    @require_initialize
    def make_wheel_cache(self) -> shims.WheelCache:
        return shims.WheelCache(
            self.cache_dir.as_posix(), shims.FormatControl(set(), set()),
        )

    @require_initialize
    def make_candidate_info_cache(self) -> CandidateInfoCache:
        python_hash = hashlib.sha1(
            str(self.project.python_requires).encode()
        ).hexdigest()
        file_name = f"package_meta_{python_hash}.json"
        return CandidateInfoCache(self.cache_dir / file_name)

    @require_initialize
    def make_hash_cache(self) -> HashCache:
        return HashCache(directory=self.cache("hashes").as_posix())


context = Context()
