import functools
from pathlib import Path
from typing import Any

from cachecontrol.adapter import CacheControlAdapter
from requests_toolbelt.utils import user_agent
from unearth.session import InsecureMixin, PyPISession

from pdm.__version__ import __version__


class InsecureCacheControlAdapter(InsecureMixin, CacheControlAdapter):
    pass


class PDMSession(PyPISession):
    def __init__(self, *, cache_dir: Path, **kwargs: Any) -> None:
        from pdm.models.caches import SafeFileCache

        cache = SafeFileCache(str(cache_dir))
        self.secure_adapter_cls = functools.partial(CacheControlAdapter, cache=cache)
        self.insecure_adapter_cls = functools.partial(
            InsecureCacheControlAdapter, cache=cache
        )
        super().__init__(**kwargs)
        self.headers["User-Agent"] = self._make_user_agent()

    def _make_user_agent(self) -> str:
        return (
            user_agent.UserAgentBuilder("pdm", __version__)
            .include_implementation()
            .build()
        )
