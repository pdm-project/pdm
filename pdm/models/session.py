import functools
from pathlib import Path
from typing import Any

from cachecontrol.adapter import CacheControlAdapter
from cachecontrol.caches import FileCache
from unearth.session import InsecureMixin, PyPISession


class InsecureCacheControlAdapter(InsecureMixin, CacheControlAdapter):
    pass


class PDMSession(PyPISession):
    def __init__(self, *, cache_dir: Path, **kwargs: Any) -> None:
        self.secure_adapter_cls = functools.partial(
            CacheControlAdapter, cache=FileCache(str(cache_dir))
        )
        self.insecure_adapter_cls = functools.partial(
            InsecureCacheControlAdapter, cache=FileCache(str(cache_dir))
        )
        super().__init__(**kwargs)
