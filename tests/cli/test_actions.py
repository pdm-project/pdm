from unittest.mock import MagicMock

import pytest
from httpx2 import ConnectTimeout, Timeout

from pdm.cli.actions import get_latest_pdm_version_from_pypi


def test_get_latest_pdm_version_success(monkeypatch, mocker):
    mock_finder = mocker.MagicMock()
    mock_candidate = mocker.MagicMock()
    mock_candidate.version = "2.13.0"
    mock_finder.find_best_match.return_value.best = mock_candidate

    mock_env = mocker.MagicMock()
    mock_env.session._timeout = Timeout(30)

    mock_env.get_finder.return_value.__enter__.return_value = mock_finder

    monkeypatch.setattr(
        "pdm.cli.actions.BareEnvironment",
        lambda project: mock_env,
    )

    result = get_latest_pdm_version_from_pypi(MagicMock())

    assert result == "2.13.0"
    assert mock_env.session._timeout == Timeout(30)


def test_get_latest_pdm_version_timeout(monkeypatch, mocker):
    mock_env = mocker.MagicMock()
    mock_env.session._timeout = Timeout(30)

    mock_finder = mocker.MagicMock()
    mock_finder.find_best_match.side_effect = ConnectTimeout("connection timed out")

    mock_env.get_finder.return_value.__enter__.return_value = mock_finder

    monkeypatch.setattr(
        "pdm.cli.actions.BareEnvironment",
        lambda project: mock_env,
    )

    with pytest.raises(ConnectTimeout):
        get_latest_pdm_version_from_pypi(MagicMock())

    assert mock_env.session._timeout == Timeout(30)
