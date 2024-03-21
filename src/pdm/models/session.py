from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import hishel
import msgpack
from hishel._serializers import Metadata
from httpcore import Request, Response
from unearth.fetchers import PyPIClient

from pdm.__version__ import __version__
from pdm.termui import logger

if TYPE_CHECKING:
    from ssl import SSLContext

    from httpx import Response as HTTPXResponse


def _create_truststore_ssl_context() -> SSLContext | None:
    if sys.version_info < (3, 10):
        return None

    try:
        import ssl
    except ImportError:
        logger.warning("Disabling truststore since ssl support is missing")
        return None

    try:
        import truststore
    except ImportError:
        return None

    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


CACHES_TTL = 7 * 24 * 60 * 60  # 7 days


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
    def __init__(self, *, cache_dir: Path, **kwargs: Any) -> None:
        storage = hishel.FileStorage(serializer=MsgPackSerializer(), base_path=cache_dir, ttl=CACHES_TTL)
        controller = hishel.Controller()
        kwargs.setdefault("verify", _create_truststore_ssl_context() or True)
        kwargs.setdefault("follow_redirects", True)

        super().__init__(**kwargs)
        self.headers["User-Agent"] = self._make_user_agent()
        self.event_hooks["response"].append(self.on_response)

        self._transport = hishel.CacheTransport(self._transport, storage, controller)  # type: ignore[has-type]
        for name, transport in self._mounts.items():
            if name.scheme == "file" or transport is None:
                # don't cache file:// transport
                continue
            self._mounts[name] = hishel.CacheTransport(transport, storage, controller)

    def _make_user_agent(self) -> str:
        import platform

        return "pdm/{} {}/{} {}/{}".format(
            __version__,
            platform.python_implementation(),
            platform.python_version(),
            platform.system(),
            platform.release(),
        )

    def on_response(self, response: HTTPXResponse) -> None:
        from unearth.utils import ARCHIVE_EXTENSIONS

        if response.extensions.get("from_cache") and response.url.path.endswith(ARCHIVE_EXTENSIONS):
            logger.info("Using cached response for %s", response.url)
