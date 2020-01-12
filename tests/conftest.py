import os
import shutil
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlparse

import pip_shims
from pip._internal.vcs import versioncontrol
from pip._vendor import requests

import pytest
from pdm.context import context
from pdm.models.candidates import Candidate
from pdm.models.repositories import BaseRepository
from pdm.models.requirements import Requirement
from pdm.models.specifiers import PySpecSet
from pdm.types import Source
from pdm.utils import get_finder
from tests import FIXTURES


class ArtifactoryAdaptor(requests.adapters.BaseAdapter):
    def __init__(self, base_path):
        super().__init__()
        self.base_path = base_path
        self._opened_files = []

    def send(
        self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None
    ):
        file_path = self.base_path / urlparse(request.url).path.lstrip(
            "/"
        )  # type: Path
        response = requests.models.Response()
        response.request = request
        if not file_path.exists():
            response.status_code = 404
            response.reason = "Not Found"
            response.raw = BytesIO(b"Not Found")
        else:
            response.status_code = 200
            response.reason = "OK"
            response.raw = file_path.open("rb")
        self._opened_files.append(response.raw)
        return response

    def close(self):
        for fp in self._opened_files:
            fp.close()
        self._opened_files.clear()


class MockVersionControl(versioncontrol.VersionControl):
    def obtain(self, dest, url):
        url, _ = self.get_url_rev_options(url)
        path = os.path.splitext(os.path.basename(urlparse(str(url)).path))[0]
        mocked_path = FIXTURES / "projects" / path
        shutil.copytree(mocked_path, dest)


class TestRepository(BaseRepository):
    def get_dependencies(
        self, candidate: Candidate
    ) -> Tuple[List[Requirement], PySpecSet, str]:
        pass

    def _find_named_matches(
        self,
        requirement: Requirement,
        requires_python: PySpecSet,
        allow_prereleases: bool = False,
    ) -> List[Candidate]:
        pass

    @contextmanager
    def get_finder(
        self, sources: Optional[List[Source]] = None
    ) -> pip_shims.PackageFinder:
        sources = sources or self.sources
        finder = get_finder(sources, context.cache_dir.as_posix())
        finder.session.mount("http://fixtures.test/", ArtifactoryAdaptor(FIXTURES))
        yield finder
        finder.session.close()


class FakeProject:
    pass


@pytest.fixture()
def repository():
    return TestRepository([])


@pytest.fixture()
def project(tmp_path):
    p = FakeProject()
    p.config = {"cache_dir": tmp_path.as_posix()}
    p.packages_root = None
    p.python_requires = PySpecSet(">=3.6")
    context.init(p)
    return p


@pytest.fixture()
def vcs(mocker):
    ret = MockVersionControl()
    mocker.patch(
        "pip._internal.vcs.versioncontrol.VcsSupport.get_backend", return_value=ret
    )
    mocker.patch("pip._internal.download._get_used_vcs_backend", return_value=ret)
    yield ret


@pytest.fixture(params=[False, True])
def is_editable(request):
    return request.param
