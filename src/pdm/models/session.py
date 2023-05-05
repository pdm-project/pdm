import functools
from pathlib import Path
from typing import Any

from cachecontrol.adapter import CacheControlAdapter
from cachecontrol.serialize import Serializer as LegacySerializer
from requests_toolbelt.utils import user_agent
from unearth.session import InsecureMixin, PyPISession

from pdm.__version__ import __version__


class Serializer(LegacySerializer):
    def dumps(self, request, response, body=None):  # type: ignore[no-untyped-def]
        if not hasattr(response, "strict"):
            # XXX: urllib3 2.0 removes this attribute
            response.strict = False
        return super().dumps(request, response, body)

    def prepare_response(self, request, cached, body_file=None):  # type: ignore[no-untyped-def]
        # We don't need to pass strict to HTTPResponse
        cached["response"].pop("strict", None)
        return super().prepare_response(request, cached, body_file)


class InsecureCacheControlAdapter(InsecureMixin, CacheControlAdapter):
    pass


class PDMSession(PyPISession):
    def __init__(self, *, cache_dir: Path, **kwargs: Any) -> None:
        from pdm.models.caches import SafeFileCache

        cache = SafeFileCache(str(cache_dir))
        serializer = Serializer()
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
