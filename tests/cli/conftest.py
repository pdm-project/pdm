from __future__ import annotations

import shutil
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from pytest_mock import MockerFixture

from pdm.cli.commands.publish.package import PackageFile
from pdm.cli.commands.publish.repository import Repository
from pdm.models.auth import Keyring, keyring
from tests import FIXTURES


@pytest.fixture
def mock_run_gpg(mocker: MockerFixture):
    def mock_run_gpg(args):
        signature_file = args[-1] + ".asc"
        with open(signature_file, "wb") as f:
            f.write(b"fake signature")

    mocker.patch.object(PackageFile, "_run_gpg", side_effect=mock_run_gpg)


@pytest.fixture
def prepare_packages(tmp_path: Path):
    dist_path = tmp_path / "dist"
    dist_path.mkdir()
    for filename in [
        "demo-0.0.1-py2.py3-none-any.whl",
        "demo-0.0.1.tar.gz",
        "demo-0.0.1.zip",
    ]:
        shutil.copy2(FIXTURES / "artifacts" / filename, dist_path)


@pytest.fixture
def mock_pypi(mocker: MockerFixture):
    def send(request, **kwargs):
        # consume the data body to make the progress complete
        request.read()
        return httpx.Response(status_code=200, request=request)

    return mocker.patch("pdm.models.session.PDMPyPIClient.send", side_effect=send)


@pytest.fixture
def uploaded(mocker: MockerFixture):
    packages = []

    def fake_upload(package):
        packages.append(package)
        return httpx.Response(status_code=200, request=httpx.Request("POST", "https://upload.pypi.org/legacy/"))

    mocker.patch.object(Repository, "upload", side_effect=fake_upload)
    return packages


@dataclass
class PublishMock:
    mock_pypi: MagicMock
    uploaded: list[Any]


@pytest.fixture
# @pytest.mark.usefixtures("mock_run_gpg", "prepare_packages")
def mock_publish(mock_pypi, uploaded) -> PublishMock:
    return PublishMock(
        mock_pypi=mock_pypi,
        uploaded=uploaded,
    )


@pytest.fixture
def _echo(project):
    """
    Provides an echo.py script producing cross-platform expectable outputs
    """
    (project.root / "echo.py").write_text(
        textwrap.dedent(
            """\
            import os, sys, io
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, newline='\\n')
            name = sys.argv[1]
            vars = " ".join([f"{v}={os.getenv(v)}" for v in sys.argv[2:]])
            print(f"{name} CALLED with {vars}" if vars else f"{name} CALLED")
            """
        )
    )


@pytest.fixture(name="keyring")
def keyring_fixture(mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> Keyring:
    from unearth.auth import AuthInfo, KeyringBaseProvider

    class MockKeyringProvider(KeyringBaseProvider):
        def __init__(self) -> None:
            self._store: dict[str, dict[str, str]] = {}

        def save_auth_info(self, url: str, username: str, password: str) -> None:
            self._store.setdefault(url, {})[username] = password

        def get_auth_info(self, url: str, username: str | None) -> AuthInfo | None:
            d = self._store.get(url, {})
            if username is not None and username in d:
                return username, d[username]
            if username is None and d:
                return next(iter(d.items()))
            return None

        def delete_auth_info(self, url: str, username: str) -> None:
            self._store.get(url, {}).pop(username, None)

    provider = MockKeyringProvider()
    mocker.patch("unearth.auth.get_keyring_provider", return_value=provider)
    monkeypatch.setattr(keyring, "provider", provider)
    monkeypatch.setattr(keyring, "enabled", True)
    return keyring
