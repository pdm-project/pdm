import json
import os
import shutil
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

import pip_shims
from pip._internal.vcs import versioncontrol
from pip._vendor import requests
from pip._vendor.pkg_resources import safe_name

import pytest
from pdm.context import context
from pdm.exceptions import CandidateInfoNotFound
from pdm.models.candidates import Candidate
from pdm.models.repositories import BaseRepository
from pdm.models.requirements import Requirement
from pdm.models.specifiers import PySpecSet
from pdm.types import CandidateInfo, Source
from pdm.utils import get_finder
from tests import FIXTURES


class LocalFileAdapter(requests.adapters.BaseAdapter):
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
    def __init__(self, sources):
        super().__init__(sources)
        self._pypi_data = {}
        self.load_fixtures()

    def add_candidate(self, name, version, requires_python=""):
        pypi_data = self._pypi_data.setdefault(safe_name(name), {}).setdefault(
            version, {}
        )
        pypi_data["requires_python"] = requires_python

    def add_dependencies(self, name, version, requirements):
        pypi_data = self._pypi_data[safe_name(name)][version]
        pypi_data.setdefault("dependencies", []).extend(requirements)

    def _get_dependencies_from_fixture(
        self, candidate: Candidate
    ) -> Tuple[List[str], str, str]:
        try:
            pypi_data = self._pypi_data[candidate.req.key][candidate.version]
        except KeyError:
            raise CandidateInfoNotFound(candidate)
        deps = pypi_data.get("dependencies", [])
        for extra in candidate.req.extras or ():
            deps.extend(pypi_data.get("extras_require", {}).get(extra, []))
        return deps, pypi_data.get("requires_python", ""), ""

    def dependency_generators(self) -> Iterable[Callable[[Candidate], CandidateInfo]]:
        return (
            self._get_dependencies_from_cache,
            self._get_dependencies_from_fixture,
            self._get_dependencies_from_metadata,
        )

    def get_hashes(self, candidate: Candidate) -> None:
        candidate.hashes = {}

    def _find_named_matches(
        self,
        requirement: Requirement,
        requires_python: PySpecSet = PySpecSet(),
        allow_prereleases: Optional[bool] = None,
        allow_all: bool = False,
    ) -> List[Candidate]:
        if allow_prereleases is None:
            allow_prereleases = requirement.allow_prereleases

        cans = []
        for version, candidate in self._pypi_data.get(requirement.key, {}).items():
            c = Candidate(
                requirement, self, name=requirement.project_name, version=version
            )
            c._requires_python = PySpecSet(candidate.get("requires_python", ""))
            cans.append(c)

        sorted_cans = sorted(
            (
                c
                for c in cans
                if requirement.specifier.contains(c.version, allow_prereleases)
            ),
            key=lambda c: c.version,
        )
        if not allow_all:
            sorted_cans = [
                can
                for can in sorted_cans
                if requires_python.is_subset(can.requires_python)
            ]
        if not sorted_cans and allow_prereleases is None:
            # No non-pre-releases is found, force pre-releases now
            sorted_cans = sorted(
                (c for c in cans if requirement.specifier.contains(c.version, True)),
                key=lambda c: c.version,
            )
        return sorted_cans

    @contextmanager
    def get_finder(
        self,
        sources: Optional[List[Source]] = None,
        requires_python: Optional[PySpecSet] = None,
        ignore_requires_python: bool = False,
    ) -> pip_shims.PackageFinder:
        sources = sources or self.sources

        finder = get_finder(
            sources,
            context.cache_dir.as_posix(),
            requires_python.max_major_minor_version() if requires_python else None,
            ignore_requires_python,
        )
        finder.session.mount("http://fixtures.test/", LocalFileAdapter(FIXTURES))
        yield finder
        finder.session.close()

    def load_fixtures(self):
        json_file = FIXTURES / "pypi.json"
        self._pypi_data = json.loads(json_file.read_text())


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
