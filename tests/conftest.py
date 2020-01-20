import json
import os
import shutil
from io import BytesIO
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

import crayons
from pip._internal.vcs import versioncontrol
from pip._vendor import requests
from pip._vendor.pkg_resources import safe_name

import pytest
from pdm.exceptions import CandidateInfoNotFound
from pdm.installers import Synchronizer
from pdm.models.candidates import Candidate
from pdm.models.repositories import BaseRepository
from pdm.models.requirements import Requirement
from pdm.models.specifiers import PySpecSet
from pdm.project import Project
from pdm._types import CandidateInfo
from pdm.utils import get_finder
from tests import FIXTURES

crayons.disable()


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

    @classmethod
    def get_revision(cls, location):
        return "1234567890abcdef"


class TestRepository(BaseRepository):
    def __init__(self, sources, environment):
        super().__init__(sources, environment)
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
                requirement,
                self.environment,
                name=requirement.project_name,
                version=version,
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

    def load_fixtures(self):
        json_file = FIXTURES / "pypi.json"
        self._pypi_data = json.loads(json_file.read_text())


class TestProject(Project):
    pass


class MockSynchronizer(Synchronizer):
    def __init__(self):
        super().__init__({}, None)
        self.working_set = {}

    def compare_with_working_set(self):
        working_set = self.working_set
        to_update, to_remove = [], []
        environment = self.environment.marker_environment()
        candidates = self.candidates.copy()
        for key, version in working_set.items():
            if key not in candidates:
                to_remove.append(key)
            else:
                can = candidates.pop(key)
                if can.marker and not can.marker.evaluate(environment):
                    to_remove.append(key)
                elif version != can.version:
                    to_update.append(key)
        to_add = [
            name
            for name, can in candidates.items()
            if not (can.marker and not can.marker.evaluate(environment))
        ]
        return to_add, to_update, to_remove

    def install_candidates(self, candidates):
        self.working_set.update({can.req.key: can.version for can in candidates})

    def remove_distributions(self, distributions):
        for dist in distributions:
            try:
                del self.working_set[dist]
            except KeyError:
                pass


def get_local_finder(*args, **kwargs):
    finder = get_finder(*args, **kwargs)
    finder.session.mount("http://fixtures.test/", LocalFileAdapter(FIXTURES))
    return finder


@pytest.fixture()
def project(tmp_path, mocker):
    p = TestProject(tmp_path.as_posix())
    p.config["cache_dir"] = tmp_path.joinpath("caches").as_posix()
    mocker.patch("pdm.utils.get_finder", get_local_finder)
    mocker.patch("pdm.models.environment.get_finder", get_local_finder)
    mocker.patch("pdm.cli.commands.Project", return_value=p)
    p.init_pyproject()
    return p


@pytest.fixture()
def repository(project):
    rv = TestRepository([], project.environment)
    project.get_repository = lambda: rv
    return rv


@pytest.fixture()
def synchronizer(mocker):
    rv = MockSynchronizer()

    def new_synchronizer(candidates, environment):
        rv.candidates = candidates
        rv.environment = environment
        return rv

    mocker.patch("pdm.cli.actions.Synchronizer", new_synchronizer)
    yield rv


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


@pytest.fixture(params=[False, True])
def is_dev(request):
    return request.param
