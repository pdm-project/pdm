from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Iterable
from urllib.parse import unquote, urlparse

import pytest
from unearth.vcs import Git, vcs_support

from pdm.models.auth import keyring
from pdm.project import Project
from pdm.utils import path_to_url
from tests import FIXTURES

if TYPE_CHECKING:
    from pdm.pytest import IndexesDefinition


os.environ.update(CI="1", PDM_CHECK_UPDATE="0")

pytest_plugins = [
    "pdm.pytest",
]


@pytest.fixture
def index() -> dict[str, bytes]:
    return {}


@pytest.fixture(scope="session", autouse=True)
def disable_keyring():
    keyring.enabled = False


@pytest.fixture
def pypi_indexes(index) -> IndexesDefinition:
    return {
        "http://fixtures.test/": {
            "/": FIXTURES,
        },
        "https://my.pypi.org/": (
            {
                "/simple": FIXTURES / "index",
                "/json": FIXTURES / "json",
            },
            index,
            True,
        ),
    }


class MockGit(Git):
    def fetch_new(self, location, url, rev, args):
        path = os.path.splitext(os.path.basename(unquote(urlparse(str(url)).path)))[0]
        mocked_path = FIXTURES / "projects" / path
        shutil.copytree(mocked_path, location)

    def get_revision(self, location: Path) -> str:
        return "1234567890abcdef"

    def is_immutable_revision(self, location, link) -> bool:
        rev = self.get_url_and_rev_options(link)[1]
        return rev == "1234567890abcdef"


@pytest.fixture
def repository_pypi_json() -> Path:
    return FIXTURES / "pypi.json"


@pytest.fixture(scope="session")
def build_env_wheels() -> Iterable[Path]:
    return [
        FIXTURES / "artifacts" / wheel_name
        for wheel_name in (
            "pdm_pep517-1.0.0-py3-none-any.whl",
            "poetry_core-1.3.2-py3-none-any.whl",
            "setuptools-68.0.0-py3-none-any.whl",
            "wheel-0.37.1-py2.py3-none-any.whl",
            "flit_core-3.6.0-py3-none-any.whl",
            "pdm_backend-2.1.4-py3-none-any.whl",
            "importlib_metadata-4.8.3-py3-none-any.whl",
            "zipp-3.7.0-py3-none-any.whl",
            "typing_extensions-4.4.0-py3-none-any.whl",
        )
    ]


@pytest.fixture
def local_finder_artifacts() -> Path:
    return FIXTURES / "artifacts"


def copytree(src: Path, dst: Path) -> None:
    if not dst.exists():
        dst.mkdir(parents=True)
    for subpath in src.iterdir():
        if subpath.is_dir():
            copytree(subpath, dst / subpath.name)
        else:
            shutil.copy2(subpath, dst)


@pytest.fixture()
def fixture_project(project_no_init: Project, request: pytest.FixtureRequest, local_finder_artifacts: Path):
    """Initialize a project from a fixture project"""

    def func(project_name):
        source = FIXTURES / "projects" / project_name
        copytree(source, project_no_init.root)
        project_no_init.pyproject.reload()
        if "local_finder" in request.fixturenames:
            artifacts_dir = str(local_finder_artifacts)
            project_no_init.pyproject.settings["source"] = [
                {
                    "type": "find_links",
                    "verify_ssl": False,
                    "url": path_to_url(artifacts_dir),
                    "name": "pypi",
                }
            ]
            project_no_init.pyproject.write()
        project_no_init.environment = None
        return project_no_init

    return func


@pytest.fixture()
def vcs(monkeypatch):
    monkeypatch.setattr(vcs_support, "_registry", {"git": MockGit})
    return


@pytest.fixture(params=[False, True])
def is_editable(request):
    return request.param


@pytest.fixture(params=[False, True])
def dev_option(request) -> Iterable[str]:
    return ("--dev",) if request.param else ()
