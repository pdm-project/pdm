from functools import wraps
from pathlib import Path
from pip_shims import shims

from pdm.exceptions import ProjectNotInitialized


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
        path.mkdir(exist_ok=True)
        return path

    @require_initialize
    def make_wheel_cache(self) -> shims.WheelCache:
        return shims.WheelCache(
            self.cache_dir.as_posix(), shims.FormatControl(set(), set()),
        )


context = Context()
