from __future__ import annotations

import shutil
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import requests
from pytest_mock import MockerFixture

from pdm.cli.commands.publish.package import PackageFile
from pdm.cli.commands.publish.repository import Repository
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
    def post(url, *, data, **kwargs):
        # consume the data body to make the progress complete
        data.read()
        resp = requests.Response()
        resp.status_code = 200
        resp.reason = "OK"
        resp.url = url
        return resp

    return mocker.patch("pdm.models.session.PDMSession.post", side_effect=post)


@pytest.fixture
def uploaded(mocker: MockerFixture):
    packages = []

    def fake_upload(package, progress):
        packages.append(package)
        resp = requests.Response()
        resp.status_code = 200
        resp.reason = "OK"
        resp.url = "https://upload.pypi.org/legacy/"
        return resp

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
