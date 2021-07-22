import collections
import functools
import json
import os
import re
import shutil
import sys
from distutils.dir_util import copy_tree
from io import BytesIO
from pathlib import Path
from typing import Callable, Iterable, List, Tuple
from urllib.parse import urlparse

import pytest
from click.testing import CliRunner
from pip._internal.vcs import versioncontrol
from pip._vendor import requests
from pip._vendor.pkg_resources import WorkingSet

from pdm._types import CandidateInfo
from pdm.cli.actions import do_init, do_use
from pdm.core import Core
from pdm.exceptions import CandidateInfoNotFound
from pdm.models.candidates import Candidate
from pdm.models.environment import Environment
from pdm.models.repositories import BaseRepository
from pdm.models.requirements import Requirement, filter_requirements_with_extras
from pdm.project import Project
from pdm.project.config import Config
from pdm.utils import cached_property, get_finder, normalize_name, temp_environ
from tests import FIXTURES

os.environ["CI"] = "1"
main = Core()


class LocalFileAdapter(requests.adapters.BaseAdapter):
    def __init__(self, base_path):
        super().__init__()
        self.base_path = base_path
        self._opened_files = []

    def send(
        self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None
    ):
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

    def is_immutable_rev_checkout(self, url: str, dest: str) -> bool:
        if "@1234567890abcdef" in url:
            return True
        return super().is_immutable_rev_checkout(url, dest)


class _FakeLink:
    is_wheel = False


class TestRepository(BaseRepository):
    def __init__(self, sources, environment):
        super().__init__(sources, environment)
        self._pypi_data = {}
        self.load_fixtures()

    def add_candidate(self, name, version, requires_python=""):
        pypi_data = self._pypi_data.setdefault(normalize_name(name), {}).setdefault(
            version, {}
        )
        pypi_data["requires_python"] = requires_python

    def add_dependencies(self, name, version, requirements):
        pypi_data = self._pypi_data[normalize_name(name)][version]
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

    def load_fixtures(self):
        json_file = FIXTURES / "pypi.json"
        self._pypi_data = json.loads(json_file.read_text())


class TestProject(Project):
    def __init__(self, core, root_path, is_global):
        self.root_path = Path(root_path or ".")
        self.GLOBAL_PROJECT = self.root_path / ".pdm-home" / "global-project"
        super().__init__(core, root_path, is_global)

    @cached_property
    def global_config(self):
        return Config(self.root_path / ".pdm-home" / "config.toml", is_global=True)


main.project_class = TestProject


class Distribution:
    def __init__(self, key, version, editable=False):
        self.key = self.project_name = key
        self.version = version
        self.editable = editable
        self.dependencies = []

    def as_req(self):
        return f"{self.key}=={self.version}\n"

    def requires(self, extras=()):
        return self.dependencies


class MockWorkingSet(collections.abc.MutableMapping):
    def __init__(self, *args, **kwargs):
        self.pkg_ws = WorkingSet([])
        self._data = {}

    def add_distribution(self, dist):
        self._data[dist.key] = dist

    def __getitem__(self, key):
        return self._data[key]

    def __len__(self):
        return len(self._data)

    def __iter__(self):
        return iter(self._data)

    def __setitem__(self, key, value):
        self._data[key] = value

    def __delitem__(self, key):
        del self._data[key]


@pytest.fixture()
def working_set(mocker, repository):
    from pdm.models.pip_shims import pip_logging

    rv = MockWorkingSet()
    mocker.patch.object(Environment, "get_working_set", return_value=rv)

    def install(candidate):
        pip_logging._log_state.indentation = 0
        dependencies = repository.get_dependencies(candidate)[0]
        key = normalize_name(candidate.name)
        dist = Distribution(key, candidate.version, candidate.req.editable)
        dist.dependencies = dependencies
        rv.add_distribution(dist)

    def uninstall(dist):
        del rv[dist.key]

    installer = mocker.MagicMock()
    installer.install.side_effect = install
    installer.uninstall.side_effect = uninstall
    mocker.patch("pdm.installers.synchronizers.Installer", return_value=installer)
    mocker.patch("pdm.installers.Installer", return_value=installer)

    yield rv


def get_local_finder(*args, **kwargs):
    finder = get_finder(*args, **kwargs)
    finder.session.mount("http://fixtures.test/", LocalFileAdapter(FIXTURES))
    return finder


@pytest.fixture(autouse=True)
def pip_global_tempdir_manager():
    from pdm.models.pip_shims import global_tempdir_manager

    with global_tempdir_manager():
        yield


def remove_pep582_path_from_pythonpath(pythonpath):
    """Remove all pep582 paths of PDM from PYTHONPATH"""
    paths = pythonpath.split(os.pathsep)
    paths = [path for path in paths if "pdm/pep582" not in path]
    return os.pathsep.join(paths)


@pytest.fixture()
def project_no_init(tmp_path, mocker):
    p = main.create_project(tmp_path)
    mocker.patch("pdm.utils.get_finder", get_local_finder)
    mocker.patch("pdm.models.environment.get_finder", get_local_finder)
    mocker.patch("pdm.project.core.Config.HOME_CONFIG", tmp_path)
    old_config_map = Config._config_map.copy()
    p.global_config["cache_dir"] = tmp_path.joinpath("caches").as_posix()
    do_use(p, getattr(sys, "_base_executable", sys.executable))
    with temp_environ():
        os.environ.pop("VIRTUAL_ENV", None)
        os.environ.pop("PEP582_PACKAGES", None)
        pythonpath = os.environ.pop("PYTHONPATH", "")
        pythonpath = remove_pep582_path_from_pythonpath(pythonpath)
        if pythonpath:
            os.environ["PYTHONPATH"] = pythonpath
        yield p
    # Restore the config items
    Config._config_map = old_config_map


@pytest.fixture()
def project(project_no_init):
    do_init(project_no_init, "test_project", "0.0.0")
    # Clean the cached property
    project_no_init._environment = None
    return project_no_init


@pytest.fixture()
def fixture_project(project_no_init):
    """Initailize a project from a fixture project"""

    def func(project_name):
        source = FIXTURES / "projects" / project_name
        copy_tree(source.as_posix(), project_no_init.root.as_posix())
        project_no_init._pyproject = None
        return project_no_init

    return func


@pytest.fixture()
def repository(project, mocker):
    rv = TestRepository([], project.environment)
    mocker.patch.object(project, "get_repository", return_value=rv)
    return rv


@pytest.fixture()
def vcs(mocker):
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
def is_editable(request):
    return request.param


@pytest.fixture(params=[False, True])
def is_dev(request):
    return request.param


@pytest.fixture()
def invoke():
    runner = CliRunner(mix_stderr=False)
    return functools.partial(runner.invoke, main, prog_name="pdm")


@pytest.fixture()
def core():
    return main


@pytest.fixture()
def index():
    from pip._internal.index.collector import HTMLPage, LinkCollector

    old_fetcher = LinkCollector.fetch_page

    def fetch_page(self, location):
        m = re.search(r"/simple/([^/]+)/?", location.url)
        if not m:
            return old_fetcher(self, location)
        path = FIXTURES / "index" / (m.group(1) + ".html")
        return HTMLPage(path.read_bytes(), "utf-8", location.url)

    LinkCollector.fetch_page = fetch_page
    return
