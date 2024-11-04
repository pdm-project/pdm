from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pdm.project.core import Project


def test_session_sources_all_proxy(project: Project, mocker, monkeypatch):
    monkeypatch.setenv("all_proxy", "http://localhost:8888")
    mock_get_transport = mocker.patch("pdm.models.session._get_transport")

    assert project.environment.session is not None
    transport_args = mock_get_transport.call_args
    assert transport_args is not None
    assert transport_args.kwargs["proxy"].url == "http://localhost:8888"

    monkeypatch.setenv("no_proxy", "pypi.org")
    mock_get_transport.reset_mock()
    del project.environment.session
    assert project.environment.session is not None
    transport_args = mock_get_transport.call_args
    assert transport_args is not None
    assert transport_args.kwargs["proxy"] is None
