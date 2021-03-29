import collections
import functools
import json
import os
import shutil
import sys
from collections import OrderedDict
from distutils.dir_util import copy_tree
from io import BytesIO
from pathlib import Path, PosixPath
from typing import Any, Callable, Iterable, Iterator, List, Optional, Tuple, Union
from urllib.parse import urlparse

import pytest
from _pytest.fixtures import SubRequest
from click.testing import CliRunner
from pip._internal.index.package_finder import PackageFinder
from pip._internal.utils.misc import HiddenText
from pip._internal.vcs import versioncontrol
from pip._vendor import requests
from pip._vendor.pkg_resources import safe_name
from pip._vendor.requests.models import PreparedRequest, Response
from pytest_mock.plugin import MockerFixture
from tomlkit.items import Bool, String

from pdm._types import CandidateInfo
from pdm.cli.actions import do_init, do_use
from pdm.core import Core
from pdm.exceptions import CandidateInfoNotFound
from pdm.models.candidates import Candidate
from pdm.models.environment import Environment
from pdm.models.repositories import BaseRepository
from pdm.models.requirements import (
    NamedRequirement,
    Requirement,
    filter_requirements_with_extras,
)
from pdm.project import Project
from pdm.project.config import Config
from pdm.utils import cached_property, get_finder, temp_environ
from tests import FIXTURES

os.environ["CI"] = "1"
main = Core()


class LocalFileAdapter(requests.adapters.BaseAdapter):
    def __init__(self, base_path: PosixPath) -> None:
        super().__init__()
        self.base_path = base_path
        self._opened_files = []

    def send(
        self,
        request: PreparedRequest,
        stream: bool = False,
        timeout: int = None,
        verify: bool = True,
        cert: Optional[Any] = None,
        proxies: OrderedDict = None,
    ) -> Response:
        file_path = self.base_path / urlparse(request.url).path.lstrip("/")
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

    def close(self) -> None:
        for fp in self._opened_files:
            fp.close()
        self._opened_files.clear()


class MockVersionControl(versioncontrol.VersionControl):
    def obtain(self, dest: str, url: HiddenText) -> None:
        url, _ = self.get_url_rev_options(url)
        path = os.path.splitext(os.path.basename(urlparse(str(url)).path))[0]
        mocked_path = FIXTURES / "projects" / path
        shutil.copytree(mocked_path, dest)

    @classmethod
    def get_revision(cls, location: Optional[str]) -> str:
        return "1234567890abcdef"


class _FakeLink:
    is_wheel = False


class TestRepository(BaseRepository):
    def __init__(self, sources: List, environment: Environment) -> None:
        super().__init__(sources, environment)
        self._pypi_data = {}
        self.load_fixtures()

    def add_candidate(self, name: str, version: str, requires_python: str = "") -> None:
        pypi_data = self._pypi_data.setdefault(safe_name(name), {}).setdefault(
            version, {}
        )
        pypi_data["requires_python"] = requires_python

    def add_dependencies(
        self, name: str, version: str, requirements: List[str]
    ) -> None:
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
        deps = filter_requirements_with_extras(deps, candidate.req.extras or ())
        return deps, pypi_data.get("requires_python", ""), ""

    def dependency_generators(self) -> Iterable[Callable[[Candidate], CandidateInfo]]:
        return (
            self._get_dependencies_from_cache,
            self._get_dependencies_from_fixture,
            self._get_dependencies_from_metadata,
        )

    def get_hashes(self, candidate: Candidate) -> None:
        candidate.hashes = {}

    def _find_candidates(self, requirement: Requirement) -> Iterable[Candidate]:
        for version, candidate in self._pypi_data.get(requirement.key, {}).items():
            c = Candidate(
                requirement,
                self.environment,
                name=requirement.project_name,
                version=version,
            )
            c.requires_python = candidate.get("requires_python", "")
            c.link = _FakeLink()
            yield c

    def load_fixtures(self) -> None:
        json_file = FIXTURES / "pypi.json"
        self._pypi_data = json.loads(json_file.read_text())


class TestProject(Project):
    def __init__(self, root_path: str) -> None:
        self.GLOBAL_PROJECT = Path(root_path) / ".pdm-home" / "global-project"
        super().__init__(root_path)

    @cached_property
    def global_config(self) -> Config:
        return Config(self.root / ".pdm-home" / "config.toml", is_global=True)


class Distribution:
    def __init__(
        self,
        key: str,
        version: Union[str, String],
        editable: Union[None, bool, Bool] = False,
    ) -> None:
        self.key = key
        self.version = version
        self.editable = editable
        self.dependencies = []

    def requires(self, extras: Tuple[()] = ()) -> List[NamedRequirement]:
        return self.dependencies


class MockWorkingSet(collections.abc.MutableMapping):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.pkg_ws = None
        self._data = {}

    def add_distribution(self, dist: Distribution) -> None:
        self._data[dist.key] = dist

    def __getitem__(self, key: str) -> Distribution:
        return self._data[key]

    def __len__(self):
        return len(self._data)

    def __iter__(self) -> Iterator:
        return iter(self._data)

    def __setitem__(self, key, value):
        self._data[key] = value

    def __delitem__(self, key: str) -> None:
        del self._data[key]


@pytest.fixture()
def working_set(
    mocker: MockerFixture, repository: TestRepository
) -> Iterator[Union[Iterator, Iterator[MockWorkingSet]]]:
    from pdm.models.pip_shims import pip_logging

    rv = MockWorkingSet()
    mocker.patch.object(Environment, "get_working_set", return_value=rv)

    def install(candidate: Candidate) -> None:
        pip_logging._log_state.indentation = 0
        dependencies = repository.get_dependencies(candidate)[0]
        key = safe_name(candidate.name).lower()
        dist = Distribution(key, candidate.version, candidate.req.editable)
        dist.dependencies = dependencies
        rv.add_distribution(dist)

    def uninstall(dist: Distribution) -> None:
        del rv[dist.key]

    installer = mocker.MagicMock()
    installer.install.side_effect = install
    installer.uninstall.side_effect = uninstall
    mocker.patch("pdm.installers.synchronizers.Installer", return_value=installer)
    mocker.patch("pdm.installers.Installer", return_value=installer)

    yield rv


def get_local_finder(*args: Any, **kwargs: Any) -> PackageFinder:
    finder = get_finder(*args, **kwargs)
    finder.session.mount("http://fixtures.test/", LocalFileAdapter(FIXTURES))
    return finder


@pytest.fixture(autouse=True)
def pip_global_tempdir_manager() -> Iterator:
    from pdm.models.pip_shims import global_tempdir_manager

    with global_tempdir_manager():
        yield


@pytest.fixture()
def project_no_init(
    tmp_path: PosixPath, mocker: MockerFixture
) -> Iterator[Union[Iterator, Iterator[TestProject]]]:
    p = TestProject(tmp_path.as_posix())
    p.core = main
    mocker.patch("pdm.utils.get_finder", get_local_finder)
    mocker.patch("pdm.models.environment.get_finder", get_local_finder)
    mocker.patch("pdm.project.core.Config.HOME_CONFIG", tmp_path)
    old_config_map = Config._config_map.copy()
    p.global_config["cache_dir"] = tmp_path.joinpath("caches").as_posix()
    do_use(p, getattr(sys, "_base_executable", sys.executable))
    with temp_environ():
        os.environ.pop("VIRTUAL_ENV", None)
        os.environ.pop("PYTHONPATH", None)
        os.environ.pop("PEP582_PACKAGES", None)
        yield p
    # Restore the config items
    Config._config_map = old_config_map


@pytest.fixture()
def project(project_no_init: TestProject) -> TestProject:
    do_init(project_no_init, "test_project", "0.0.0")
    # Clean the cached property
    project_no_init._environment = None
    return project_no_init


@pytest.fixture()
def fixture_project(project_no_init: TestProject) -> Callable:
    """Initailize a project from a fixture project"""

    def func(project_name: str) -> TestProject:
        source = FIXTURES / "projects" / project_name
        copy_tree(source.as_posix(), project_no_init.root.as_posix())
        project_no_init._pyproject = None
        return project_no_init

    return func


@pytest.fixture()
def repository(project: TestProject, mocker: MockerFixture) -> TestRepository:
    rv = TestRepository([], project.environment)
    mocker.patch.object(project, "get_repository", return_value=rv)
    return rv


@pytest.fixture()
def vcs(
    mocker: MockerFixture,
) -> Iterator[Union[Iterator, Iterator[MockVersionControl]]]:
    ret = MockVersionControl()
    mocker.patch(
        "pip._internal.vcs.versioncontrol.VcsSupport.get_backend", return_value=ret
    )
    mocker.patch(
        "pip._internal.vcs.versioncontrol.VcsSupport.get_backend_for_scheme",
        return_value=ret,
    )
    yield ret


@pytest.fixture(params=[False, True])
def is_editable(request: SubRequest) -> bool:
    return request.param


@pytest.fixture(params=[False, True])
def is_dev(request: SubRequest) -> bool:
    return request.param


@pytest.fixture()
def invoke() -> Callable:
    runner = CliRunner(mix_stderr=False)
    return functools.partial(runner.invoke, main, prog_name="pdm")


@pytest.fixture()
def core() -> Core:
    return main
