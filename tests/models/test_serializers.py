from __future__ import annotations
import pytest

import json
from datetime import datetime
from typing import TYPE_CHECKING
from hishel._serializers import Metadata
from hishel._utils import normalized_url
from httpcore import Request, Response
from pdm.exceptions import PdmException
from pdm.models.serializers import MsgPackSerializer, Encoder


def test_compatibility(project: Project, mocker, monkeypatch):
    try:
        import msgpack
    except ImportError:
        return  # Skip if 'MsgPack' not installed

    response = Response(200, headers={'key':'value'}, content=b"I'm a teapot.", extensions={'http_version': '2.0'})
    response.read()
    request = Request('POST', 'http://test.com', headers={'user-agent':''}, extensions={"timeout":10})
    metadata = Metadata(number_of_uses=1, created_at=datetime.now(), cache_key='foo')
    serializer = MsgPackSerializer()

    # dumped by msgpack, loads by msgpack is OK
    cached_bytes = serializer.dumps(response, request, metadata)
    resp, req, meta = serializer.loads(cached_bytes)
    resp.read()
    assert not cached_bytes.startswith(b'{') # Ensure that it was dumped by msgpack
    assert resp.status == response.status
    assert resp.content == response.content
    assert resp.headers == response.headers
    assert resp.extensions == response.extensions
    assert req.method == request.method
    assert req.extensions == request.extensions
    assert req.headers == request.headers
    assert meta == metadata
    
    origin_msgpack_loads = msgpack.loads
    # dumped by msgpack, loads by json will raises PdmException
    msgpack.loads = lambda data, raw: json.loads(data, object_hook=Encoder.object_hook)
    with pytest.raises(PdmException, match=r'pip install "pdm\[msgpack\]".*pdm cache clear'):
        serializer.loads(cached_bytes)

    origin_msgpack_packb = msgpack.packb
    msgpack.packb = lambda data, use_bin_type: json.dumps(data, cls=Encoder).encode()

    # dumped by json, loads by json is OK
    cached_bytes = serializer.dumps(response, request, metadata)
    assert cached_bytes.startswith(b'{') # Ensure that it was dumped by json
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
    msgpack.packb = origin_msgpack_packb 
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
