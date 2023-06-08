from __future__ import annotations

import functools
from pathlib import Path
from typing import IO, Any, Mapping

from cachecontrol.adapter import CacheControlAdapter
from cachecontrol.serialize import Serializer
from requests import Request
from requests_toolbelt.utils import user_agent
from unearth.session import InsecureMixin, PyPISession
from urllib3 import HTTPResponse

from pdm.__version__ import __version__


class InsecureCacheControlAdapter(InsecureMixin, CacheControlAdapter):
    pass


class CompatibleSerializer(Serializer):
    """We've switched the cache to SeparateBodyCache since 2.7.1, we use this serializer to
    read the old cache. However, reading the new cache with older PDM versions will still
    result in a broken cache.
    """

    def prepare_response(
        self, request: Request, cached: Mapping[str, Any], body_file: IO[bytes] | None = None
    ) -> HTTPResponse | None:
        body_raw = cached["response"].get("body")
        if not body_raw and body_file is None:
            # When we update the old cache using SeparateBodyCache, body_raw is set to empty
            # but the body_file hasn't been created yet. The cache is broken at this point.
            # return None to ignore this entry.
            return None
        return super().prepare_response(request, cached, body_file)


class PDMSession(PyPISession):
    def __init__(self, *, cache_dir: Path, **kwargs: Any) -> None:
        from pdm.models.caches import SafeFileCache

        cache = SafeFileCache(str(cache_dir))
        serializer = CompatibleSerializer()
        self.secure_adapter_cls = functools.partial(CacheControlAdapter, cache=cache, serializer=serializer)
        self.insecure_adapter_cls = functools.partial(InsecureCacheControlAdapter, cache=cache, serializer=serializer)
        super().__init__(**kwargs)
        self.headers["User-Agent"] = self._make_user_agent()

    def _make_user_agent(self) -> str:
        return user_agent.UserAgentBuilder("pdm", __version__).include_implementation().build()

    # HACK: make the sessions identical to functools.lru_cache
    # so that the same index page won't be fetched twice.
    # See unearth/collector.py:fetch_page
    def __hash__(self) -> int:
        return hash(self.headers["User-Agent"])

    def __eq__(self, __o: Any) -> bool:
        return isinstance(__o, PDMSession) and self.headers["User-Agent"] == __o.headers["User-Agent"]
