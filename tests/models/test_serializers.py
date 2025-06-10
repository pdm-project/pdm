from __future__ import annotations

import json
from datetime import datetime

import pytest
from hishel._serializers import Metadata
from httpcore import Request, Response

from pdm.models.serializers import Encoder, MsgPackSerializer


@pytest.mark.msgpack
def test_compatibility():
    try:
        import msgpack
    except ImportError:
        pytest.skip("msgpack is not installed, skipping compatibility tests")

    response = Response(200, headers={"key": "value"}, content=b"I'm a teapot.", extensions={"http_version": "2.0"})
    response.read()
    request = Request("POST", "http://test.com", headers={"user-agent": ""}, extensions={"timeout": 10})
    metadata = Metadata(number_of_uses=1, created_at=datetime.now(), cache_key="foo")
    serializer = MsgPackSerializer()

    # dumped by msgpack, loads by msgpack is OK
    cached_bytes = serializer.dumps(response, request, metadata)
    resp, req, meta = serializer.loads(cached_bytes)
    resp.read()
    assert not cached_bytes.startswith(b"{")  # Ensure that it was dumped by msgpack
    assert resp.status == response.status
    assert resp.content == response.content
    assert resp.headers == response.headers
    assert resp.extensions == response.extensions
    assert req.method == request.method
    assert req.extensions == request.extensions
    assert req.headers == request.headers
    assert meta == metadata

    # dumped by msgpack, loads by json will return None
    origin_msgpack_loads = msgpack.loads
    msgpack.loads = lambda data, raw: json.loads(data, object_hook=Encoder.object_hook)
    assert serializer.loads(cached_bytes) is None

    # dumped by json, loads by json is OK
    msgpack.packb = lambda data, use_bin_type: json.dumps(data, cls=Encoder).encode()
    cached_bytes = serializer.dumps(response, request, metadata)
    assert cached_bytes.startswith(b"{")  # Ensure that it was dumped by json
    resp, req, meta = serializer.loads(cached_bytes)
    resp.read()
    assert resp.status == response.status
    assert resp.content == response.content
    assert resp.headers == response.headers
    assert resp.extensions == response.extensions
    assert req.method == request.method
    assert req.extensions == request.extensions
    assert req.headers == request.headers
    assert meta == metadata

    # dumped by json, loads with msgpack installed is OK too
    msgpack.loads = origin_msgpack_loads
    resp, req, meta = serializer.loads(cached_bytes)
    resp.read()
    assert resp.status == response.status
    assert resp.content == response.content
    assert resp.headers == response.headers
    assert resp.extensions == response.extensions
    assert req.method == request.method
    assert req.extensions == request.extensions
    assert req.headers == request.headers
    assert meta == metadata
