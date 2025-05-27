from __future__ import annotations

from typing import Any, cast

import hishel
from hishel._serializers import Metadata
from httpcore import Request, Response

try:
    import msgpack

    packb = msgpack.packb
    pack_loads = msgpack.loads
    UnpackValueError = msgpack.UnpackValueError
except ImportError:
    import base64
    import json

    class Encoder(json.JSONEncoder):
        bytes_ident = "PDM_BYTES_OBJECT"

        def default(self, obj: Any) -> Any:
            if isinstance(obj, bytes):
                base64_string = base64.b64encode(obj).decode()
                return {"type": self.bytes_ident, "val": base64_string}
            return super().default(obj)

        @classmethod
        def object_hook(cls, obj: Any) -> Any:
            if isinstance(obj, dict) and obj.get("type") == cls.bytes_ident:
                val = obj.get("val")
                if val is not None and isinstance(val, str):
                    return base64.b64decode(val)
            return obj

    def packb(data: dict, use_bin_type: bool = True) -> bytes:
        return json.dumps(data, cls=Encoder).encode()

    def pack_loads(data: bytes, raw: bool = False) -> Any:
        return json.loads(data, object_hook=Encoder.object_hook)

    UnpackValueError = json.JSONDecodeError


class Serializer(hishel.BaseSerializer):
    KNOWN_REQUEST_EXTENSIONS = ("timeout", "sni_hostname")
    KNOWN_RESPONSE_EXTENSIONS = ("http_version", "reason_phrase")
    DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

    def dumps(self, response: Response, request: Request, metadata: Metadata) -> bytes:
        from hishel._utils import normalized_url

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
            "url": normalized_url(request.url),
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
        return cast(bytes, packb(full_dict, use_bin_type=True))

    def loads(self, data: bytes) -> tuple[Response, Request, Metadata] | None:
        from datetime import datetime

        try:
            full_dict = cast("dict[str, Any]", pack_loads(data, raw=False))
        except UnpackValueError:
            return None

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
