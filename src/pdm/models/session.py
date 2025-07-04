from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import hishel
import httpx
from unearth.fetchers import PyPIClient

from pdm.__version__ import __version__
from pdm.models.serializers import MsgPackSerializer
from pdm.termui import logger

if TYPE_CHECKING:
    from ssl import SSLContext

    from pdm._types import RepositoryConfig


def _create_truststore_ssl_context() -> SSLContext | None:
    if sys.version_info < (3, 10):
        return None

    try:
        import ssl
    except ImportError:
        return None

    try:
        import truststore
    except ImportError:
        return None

    import certifi

    ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_verify_locations(certifi.where())
    return ctx


_ssl_context = _create_truststore_ssl_context()
CACHES_TTL = 7 * 24 * 60 * 60  # 7 days
MAX_RETRIES = 4


@lru_cache(maxsize=None)
def _get_transport(
    verify: bool | SSLContext | str = True,
    cert: tuple[str, str | None] | None = None,
    proxy: httpx.Proxy | None = None,
) -> httpx.BaseTransport:
    return httpx.HTTPTransport(verify=verify, cert=cert, trust_env=True, proxy=proxy, retries=MAX_RETRIES)


class PDMPyPIClient(PyPIClient):
    def __init__(self, *, sources: list[RepositoryConfig], cache_dir: Path | None = None, **kwargs: Any) -> None:
        from httpx._utils import URLPattern
        from unearth.fetchers.sync import LocalFSTransport

        if cache_dir is None:

            def cache_transport(transport: httpx.BaseTransport) -> httpx.BaseTransport:
                return transport
        else:
            storage = hishel.FileStorage(serializer=MsgPackSerializer(), base_path=cache_dir, ttl=CACHES_TTL)
            controller = hishel.Controller()

            def cache_transport(transport: httpx.BaseTransport) -> httpx.BaseTransport:
                return hishel.CacheTransport(transport, storage, controller)

        mounts: dict[str, httpx.BaseTransport] = {"file://": LocalFSTransport()}
        self._trusted_host_ports: set[tuple[str, int | None]] = set()
        self._proxy_map = {
            URLPattern(key): proxy for key, proxy in self._get_proxy_map(None, allow_env_proxies=True).items()
        }
        self._proxy_map = dict(sorted(self._proxy_map.items()))
        for s in sources:
            assert s.url is not None
            url = httpx.URL(s.url)
            if s.verify_ssl is False:
                self._trusted_host_ports.add((url.host, url.port))
            if s.name == "pypi":
                kwargs["transport"] = self._transport_for(s)
                continue
            mounts[f"{url.scheme}://{url.netloc.decode('ascii')}/"] = cache_transport(self._transport_for(s))
        mounts.update(kwargs.pop("mounts", None) or {})
        kwargs.update(follow_redirects=True)

        httpx.Client.__init__(self, mounts=mounts, **kwargs)

        self.headers["User-Agent"] = self._make_user_agent()
        self.event_hooks["response"].append(self.on_response)
        self._transport = cache_transport(self._transport)  # type: ignore[has-type]

    def _transport_for(self, source: RepositoryConfig) -> httpx.BaseTransport:
        if source.verify_ssl is False:
            verify: str | bool | SSLContext = False
        elif source.ca_certs:
            verify = source.ca_certs
        else:
            verify = os.getenv("REQUESTS_CA_BUNDLE") or os.getenv("CURL_CA_BUNDLE") or _ssl_context or True
        if source.client_cert:
            cert = (source.client_cert, source.client_key)
        else:
            cert = None
        source_url = httpx.URL(cast(str, source.url))
        proxy = next((proxy for pattern, proxy in self._proxy_map.items() if pattern.matches(source_url)), None)
        return _get_transport(verify=verify, cert=cert, proxy=proxy)

    def _make_user_agent(self) -> str:
        import platform

        return f"pdm/{__version__} {platform.python_implementation()}/{platform.python_version()} {platform.system()}/{platform.release()}"

    def on_response(self, response: httpx.Response) -> None:
        from unearth.utils import ARCHIVE_EXTENSIONS

        if response.extensions.get("from_cache"):
            response.from_cache = True  # type: ignore[attr-defined]
            if response.url.path.endswith(ARCHIVE_EXTENSIONS):
                logger.info("Using cached response for %s", response.url)
