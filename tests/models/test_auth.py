from __future__ import annotations

import pytest

from pdm._types import RepositoryConfig
from pdm.exceptions import PdmException
from pdm.models.auth import Keyring, PdmBasicAuth
from pdm.termui import Verbosity


def test_auth_selects_closest_source(mocker):
    sources = [
        RepositoryConfig("pypi", "root", url="https://example.org/simple"),
        RepositoryConfig(
            "pypi",
            "private",
            url="https://example.org/private/simple",
            username="user",
            password="pass",
        ),
    ]
    auth = PdmBasicAuth(mocker.Mock(), sources)

    credentials, index = auth._get_auth_from_index_url("https://example.org/private/packages/demo")

    assert credentials == ("user", "pass")
    assert index == "https://example.org/private/simple/"
    assert auth._selected_source is sources[1]


def test_auth_handles_empty_and_unmatched_sources(mocker):
    auth = PdmBasicAuth(mocker.Mock(), [])
    assert auth._get_auth_from_index_url("https://example.org/simple") == (None, None)

    auth.sources = [RepositoryConfig("pypi", "other", url="https://other.org/simple")]
    assert auth._get_auth_from_index_url("https://example.org/simple") == (None, None)


def test_auth_uses_source_keyring_credentials(mocker):
    source = RepositoryConfig("pypi", "private", url="https://example.org/simple")
    source.populate_keyring_auth = mocker.Mock(
        side_effect=lambda: (
            setattr(source, "username", "keyring-user"),
            setattr(source, "password", "keyring-pass"),
        )
    )
    auth = PdmBasicAuth(mocker.Mock(), [source])
    auth._selected_source = source
    mocker.patch(
        "unearth.auth.MultiDomainBasicAuth._get_new_credentials",
        return_value=(None, None),
    )

    result = auth._get_new_credentials("https://example.org", allow_keyring=True)

    assert result == ("keyring-user", "keyring-pass")
    assert auth._selected_source is None


def test_auth_requires_verbose_mode_for_password_prompt(mocker):
    ui = mocker.Mock(verbosity=Verbosity.NORMAL)
    auth = PdmBasicAuth(ui, [])

    with pytest.raises(PdmException, match="rerun the command with `-v`"):
        auth._prompt_for_password("example.org")


def test_auth_verbose_password_prompt_delegates(mocker):
    ui = mocker.Mock(verbosity=Verbosity.DETAIL)
    auth = PdmBasicAuth(ui, [])
    parent = mocker.patch(
        "unearth.auth.MultiDomainBasicAuth._prompt_for_password",
        return_value=("user", "pass", True),
    )

    assert auth._prompt_for_password("example.org", "user") == ("user", "pass", True)
    parent.assert_called_once_with("example.org", "user")


def test_auth_warns_when_keyring_is_unavailable(mocker):
    ui = mocker.Mock()
    auth = PdmBasicAuth(ui, [])
    mocker.patch("pdm.models.auth.get_keyring_provider", return_value=None)
    parent = mocker.patch(
        "unearth.auth.MultiDomainBasicAuth._should_save_password_to_keyring",
        return_value=False,
    )

    assert auth._should_save_password_to_keyring() is False
    ui.info.assert_called_once()
    parent.assert_called_once_with()


def test_auth_does_not_warn_when_keyring_is_available(mocker):
    ui = mocker.Mock()
    auth = PdmBasicAuth(ui, [])
    mocker.patch("pdm.models.auth.get_keyring_provider", return_value=mocker.sentinel.provider)
    mocker.patch(
        "unearth.auth.MultiDomainBasicAuth._should_save_password_to_keyring",
        return_value=True,
    )

    assert auth._should_save_password_to_keyring() is True
    ui.info.assert_not_called()


@pytest.mark.parametrize("operation", ["get", "save", "delete"])
def test_keyring_disables_itself_after_provider_error(mocker, operation):
    provider = mocker.Mock()
    keyring = Keyring()
    keyring.provider = provider
    keyring.enabled = True
    method = getattr(provider, f"{operation}_auth_info")
    method.side_effect = RuntimeError("keyring failed")

    if operation == "get":
        result = keyring.get_auth_info("service", "user")
    else:
        result = getattr(keyring, f"{operation}_auth_info")(
            "service", "user", *(("pass",) if operation == "save" else ())
        )

    assert result in (None, False)
    assert keyring.enabled is False


def test_disabled_keyring_does_not_delete_credentials(mocker):
    keyring = Keyring()
    keyring.provider = mocker.Mock()
    keyring.enabled = False

    assert keyring.delete_auth_info("service", "user") is False
    keyring.provider.delete_auth_info.assert_not_called()
