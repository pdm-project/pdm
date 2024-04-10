from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import hishel
import httpx
import msgpack
from hishel._serializers import Metadata
from httpcore import Request, Response
from unearth.fetchers import PyPIClient

from pdm.__version__ import __version__
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

    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


_ssl_context = _create_truststore_ssl_context()
CACHES_TTL = 7 * 24 * 60 * 60  # 7 days


@lru_cache(maxsize=None)
def _get_transport(
    verify: bool | SSLContext | str = True, cert: tuple[str, str | None] | None = None
) -> httpx.BaseTransport:
    return httpx.HTTPTransport(verify=verify, cert=cert, trust_env=True)


class MsgPackSerializer(hishel.BaseSerializer):
    KNOWN_REQUEST_EXTENSIONS = ("timeout", "sni_hostname")
    KNOWN_RESPONSE_EXTENSIONS = ("http_version", "reason_phrase")
    DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

    def dumps(self, response: Response, request: Request, metadata: Metadata) -> bytes:
        response_dict = {
            "status": response.status,
            "headers": response.headers,
            "content": response.content,
            "extensions": {
                key: value for key, value in response.extensions.items() if key in self.KNOWN_RESPONSE_EXTENSIONS
            },
        }

        request_dict = {
            "method": request.method.decode("ascii"),
            "url": str(request.url),
            "headers": request.headers,
            "extensions": {
                key: value for key, value in request.extensions.items() if key in self.KNOWN_REQUEST_EXTENSIONS
            },
        }

        metadata_dict = {
            "cache_key": metadata["cache_key"],
            "number_of_uses": metadata["number_of_uses"],
            "created_at": metadata["created_at"].strftime(self.DATETIME_FORMAT),
        }

        full_dict = {
            "response": response_dict,
            "request": request_dict,
            "metadata": metadata_dict,
        }
        return cast(bytes, msgpack.packb(full_dict, use_bin_type=True))

    def loads(self, data: bytes) -> tuple[Response, Request, Metadata]:
        from datetime import datetime

        full_dict = cast("dict[str, Any]", msgpack.loads(data, raw=False))

        response_dict = full_dict["response"]
        request_dict = full_dict["request"]
        metadata_dict = full_dict["metadata"]
        metadata_dict["created_at"] = datetime.strptime(metadata_dict["created_at"], self.DATETIME_FORMAT)

        response = Response(
            status=response_dict["status"],
            headers=response_dict["headers"],
            content=response_dict["content"],
            extensions=response_dict["extensions"],
        )

        request = Request(
            method=request_dict["method"],
            url=request_dict["url"],
            headers=request_dict["headers"],
            extensions=request_dict["extensions"],
        )

        metadata = Metadata(
            cache_key=metadata_dict["cache_key"],
            created_at=metadata_dict["created_at"],
            number_of_uses=metadata_dict["number_of_uses"],
        )

        return response, request, metadata

    @property
    def is_binary(self) -> bool:
        return True


class PDMPyPIClient(PyPIClient):
    def __init__(self, *, sources: list[RepositoryConfig], cache_dir: Path, **kwargs: Any) -> None:
        from unearth.fetchers.sync import LocalFSTransport

        storage = hishel.FileStorage(serializer=MsgPackSerializer(), base_path=cache_dir, ttl=CACHES_TTL)
        controller = hishel.Controller()

        mounts: dict[str, httpx.BaseTransport] = {"file://": LocalFSTransport()}
        self._trusted_host_ports: set[tuple[str, int | None]] = set()
        transport: httpx.BaseTransport | None = None
        for s in sources:
            assert s.url is not None
            url = httpx.URL(s.url)
            if s.verify_ssl is False:
                self._trusted_host_ports.add((url.host, url.port))
            if s.name == "pypi":
                transport = self._transport_for(s)
                continue
            mounts[f"{url.scheme}://{url.netloc.decode('ascii')}/"] = hishel.CacheTransport(
                self._transport_for(s), storage, controller
            )
        mounts.update(kwargs.pop("mounts", None) or {})

        httpx.Client.__init__(self, mounts=mounts, follow_redirects=True, transport=transport, **kwargs)

        self.headers["User-Agent"] = self._make_user_agent()
        self.event_hooks["response"].append(self.on_response)
        self._transport = hishel.CacheTransport(self._transport, storage, controller)  # type: ignore[has-type]

    def _transport_for(self, source: RepositoryConfig) -> httpx.BaseTransport:
        if source.ca_certs:
            verify: str | bool | SSLContext = source.ca_certs
        else:
            verify = source.verify_ssl is not False and (_ssl_context or True)
        if source.client_cert:
            cert = (source.client_cert, source.client_key)
        else:
            cert = None
        return _get_transport(verify=verify, cert=cert)

    def _make_user_agent(self) -> str:
        import platform

        return "pdm/{} {}/{} {}/{}".format(
            __version__,
            platform.python_implementation(),
            platform.python_version(),
            platform.system(),
            platform.release(),
        )

    def on_response(self, response: httpx.Response) -> None:
        from unearth.utils import ARCHIVE_EXTENSIONS

        if response.extensions.get("from_cache") and response.url.path.endswith(ARCHIVE_EXTENSIONS):
            logger.info("Using cached response for %s", response.url)
