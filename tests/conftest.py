from __future__ import annotations

import collections
import functools
import json
import os
import shutil
import sys
from dataclasses import dataclass
from io import BytesIO, StringIO
from pathlib import Path
from typing import Callable, Iterable, Mapping
from urllib.parse import unquote, urlparse

import pytest
import requests
from packaging.version import parse as parse_version
from unearth.vcs import Git, vcs_support

from pdm._types import CandidateInfo
from pdm.cli.actions import do_init, do_use
from pdm.cli.hooks import HookManager
from pdm.core import Core
from pdm.exceptions import CandidateInfoNotFound
from pdm.models.candidates import Candidate
from pdm.models.environment import Environment
from pdm.models.repositories import BaseRepository
from pdm.models.requirements import (
    Requirement,
    filter_requirements_with_extras,
    parse_requirement,
)
from pdm.models.session import PDMSession
from pdm.project.config import Config
from pdm.project.core import Project
from pdm.utils import normalize_name, path_to_url
from tests import FIXTURES

os.environ.update(CI="1", PDM_CHECK_UPDATE="0")


class LocalFileAdapter(requests.adapters.BaseAdapter):
    def __init__(self, aliases, overrides=None, strip_suffix=False):
        super().__init__()
        self.aliases = sorted(
            aliases.items(), key=lambda item: len(item[0]), reverse=True
        )
        self.overrides = overrides if overrides is not None else {}
        self.strip_suffix = strip_suffix
        self._opened_files = []

    def get_file_path(self, path):
        for prefix, base_path in self.aliases:
            if path.startswith(prefix):
                file_path = base_path / path[len(prefix) :].lstrip("/")
                if not self.strip_suffix:
                    return file_path
                return next(
                    (p for p in file_path.parent.iterdir() if p.stem == file_path.name),
                    None,
                )
        return None

    def send(
        self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None
    ):
        request_path = urlparse(request.url).path
        file_path = self.get_file_path(request_path)
        response = requests.models.Response()
        response.url = request.url
        response.request = request
        if request_path in self.overrides:
            response.status_code = 200
            response.reason = "OK"
            response.raw = BytesIO(self.overrides[request_path])
            response.headers["Content-Type"] = "text/html"
        elif file_path is None or not file_path.exists():
            response.status_code = 404
            response.reason = "Not Found"
            response.raw = BytesIO(b"Not Found")
        else:
            response.status_code = 200
            response.reason = "OK"
            response.raw = file_path.open("rb")
            if file_path.suffix == ".html":
                response.headers["Content-Type"] = "text/html"
        self._opened_files.append(response.raw)
        return response

    def close(self):
        for fp in self._opened_files:
            fp.close()
        self._opened_files.clear()


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
    ) -> tuple[list[str], str, str]:
        try:
            pypi_data = self._pypi_data[candidate.req.key][candidate.version]
        except KeyError:
            raise CandidateInfoNotFound(candidate)
        deps = pypi_data.get("dependencies", [])
        deps = filter_requirements_with_extras(
            candidate.req.name, deps, candidate.req.extras or ()
        )
        return deps, pypi_data.get("requires_python", ""), ""

    def dependency_generators(self) -> Iterable[Callable[[Candidate], CandidateInfo]]:
        return (
            self._get_dependencies_from_cache,
            self._get_dependencies_from_fixture,
            self._get_dependencies_from_metadata,
        )

    def get_hashes(self, candidate: Candidate) -> dict[str, str] | None:
        return {}

    def _find_candidates(self, requirement: Requirement) -> Iterable[Candidate]:
        for version, candidate in sorted(
            self._pypi_data.get(requirement.key, {}).items(),
            key=lambda item: parse_version(item[0]),
            reverse=True,
        ):
            c = Candidate(
                requirement,
                name=requirement.project_name,
                version=version,
            )
            c.requires_python = candidate.get("requires_python", "")
            c.link = _FakeLink()
            yield c

    def load_fixtures(self):
        json_file = FIXTURES / "pypi.json"
        self._pypi_data = json.loads(json_file.read_text())


class Distribution:
    def __init__(self, key, version, editable=False):
        self.version = version
        self.link_file = "editable" if editable else None
        self.dependencies = []
        self.metadata = {"Name": key}
        self.name = key

    def as_req(self):
        return parse_requirement(f"{self.name}=={self.version}")

    @property
    def requires(self):
        return self.dependencies

    def read_text(self, path):
        return None


class MockWorkingSet(collections.abc.MutableMapping):
    def __init__(self, *args, **kwargs):
        self._data = {}

    def add_distribution(self, dist):
        self._data[dist.name] = dist

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

    rv = MockWorkingSet()
    mocker.patch.object(Environment, "get_working_set", return_value=rv)

    def install(candidate):
        dependencies = repository.get_dependencies(candidate)[0]
        key = normalize_name(candidate.name)
        dist = Distribution(key, candidate.version, candidate.req.editable)
        dist.dependencies = [dep.as_line() for dep in dependencies]
        rv.add_distribution(dist)

    def uninstall(dist):
        del rv[dist.name]

    install_manager = mocker.MagicMock()
    install_manager.install.side_effect = install
    install_manager.uninstall.side_effect = uninstall
    mocker.patch(
        "pdm.installers.Synchronizer.get_manager", return_value=install_manager
    )

    yield rv


def get_pypi_session(*args, overrides=None, **kwargs):
    session = PDMSession(*args, **kwargs)
    session.mount("http://fixtures.test/", LocalFileAdapter({"/": FIXTURES}))
    session.mount(
        "https://my.pypi.org/",
        LocalFileAdapter({"/simple": FIXTURES / "index"}, overrides, strip_suffix=True),
    )
    return session


def remove_pep582_path_from_pythonpath(pythonpath):
    """Remove all pep582 paths of PDM from PYTHONPATH"""
    paths = pythonpath.split(os.pathsep)
    paths = [path for path in paths if "pdm/pep582" not in path]
    return os.pathsep.join(paths)


@pytest.fixture()
def core():
    old_config_map = Config._config_map.copy()
    # Turn off use_venv by default, for testing
    Config._config_map["python.use_venv"].default = False
    main = Core()
    yield main
    # Restore the config items
    Config._config_map = old_config_map


@pytest.fixture()
def index():
    return {}


@pytest.fixture()
def project_no_init(tmp_path, mocker, core, index, monkeypatch):
    test_home = tmp_path / ".pdm-home"
    test_home.mkdir(parents=True)
    test_home.joinpath("config.toml").write_text(
        '[global_project]\npath = "{}"\n'.format(
            test_home.joinpath("global-project").as_posix()
        )
    )
    p = core.create_project(
        tmp_path, global_config=test_home.joinpath("config.toml").as_posix()
    )
    p.global_config["venv.location"] = str(tmp_path / "venvs")
    mocker.patch(
        "pdm.models.environment.PDMSession",
        functools.partial(get_pypi_session, overrides=index),
    )
    tmp_path.joinpath("caches").mkdir(parents=True)
    p.global_config["cache_dir"] = tmp_path.joinpath("caches").as_posix()
    do_use(
        p,
        getattr(sys, "_base_executable", sys.executable),
        HookManager(p, ["post_use"]),
    )
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.delenv("CONDA_PREFIX", raising=False)
    monkeypatch.delenv("PEP582_PACKAGES", raising=False)
    monkeypatch.delenv("NO_SITE_PACKAGES", raising=False)
    pythonpath = os.getenv("PYTHONPATH", "")
    pythonpath = remove_pep582_path_from_pythonpath(pythonpath)
    if pythonpath:
        monkeypatch.setenv("PYTHONPATH", pythonpath)
    yield p


@pytest.fixture()
def local_finder(project_no_init, mocker):
    artifacts_dir = str(FIXTURES / "artifacts")
    return_value = ["--no-index", "--find-links", artifacts_dir]
    mocker.patch("pdm.builders.base.prepare_pip_source_args", return_value=return_value)
    project_no_init.tool_settings["source"] = [
        {
            "type": "find_links",
            "verify_ssl": False,
            "url": path_to_url(artifacts_dir),
        }
    ]
    project_no_init.write_pyproject()


@pytest.fixture()
def project(project_no_init):
    hooks = HookManager(project_no_init, ["post_init"])
    do_init(project_no_init, "test_project", "0.0.0", hooks=hooks)
    # Clean the cached property
    project_no_init._environment = None
    return project_no_init


def copytree(src: Path, dst: Path) -> None:
    if not dst.exists():
        dst.mkdir(parents=True)
    for subpath in src.iterdir():
        if subpath.is_dir():
            copytree(subpath, dst / subpath.name)
        else:
            shutil.copy2(subpath, dst)


@pytest.fixture()
def fixture_project(project_no_init):
    """Initialize a project from a fixture project"""

    def func(project_name):
        source = FIXTURES / "projects" / project_name
        copytree(source, project_no_init.root)
        project_no_init._pyproject = None
        return project_no_init

    return func


@pytest.fixture()
def repository(project, mocker, local_finder):
    rv = TestRepository([], project.environment)
    mocker.patch.object(project, "get_repository", return_value=rv)
    return rv


@pytest.fixture()
def vcs(monkeypatch):
    monkeypatch.setattr(vcs_support, "_registry", {"git": MockGit})
    return


@pytest.fixture(params=[False, True])
def is_editable(request):
    return request.param


@pytest.fixture(params=[False, True])
def is_dev(request):
    return request.param


@dataclass
class RunResult:
    exit_code: int
    stdout: str
    stderr: str
    exception: Exception | None = None

    @property
    def output(self) -> str:
        return self.stdout

    @property
    def outputs(self) -> str:
        return self.stdout + self.stderr

    def print(self):
        print("# exit code:", self.exit_code)
        print("# stdout:", self.stdout, sep="\n")
        print("# stderr:", self.stderr, sep="\n")


@pytest.fixture()
def invoke(core, monkeypatch):
    def caller(
        args,
        strict: bool = False,
        input: str | None = None,
        obj: Project | None = None,
        env: Mapping[str, str] | None = None,
        **kwargs,
    ):
        __tracebackhide__ = True

        stdin = StringIO(input)
        stdout = StringIO()
        stderr = StringIO()
        exit_code = 0
        exception = None

        with monkeypatch.context() as m:
            m.setattr("sys.stdin", stdin)
            m.setattr("sys.stdout", stdout)
            m.setattr("sys.stderr", stderr)
            for key, value in (env or {}).items():
                m.setenv(key, value)
            try:
                core.main(args, "pdm", obj=obj, **kwargs)
            except SystemExit as e:
                exit_code = e.code
            except Exception as e:
                exit_code = 1
                exception = e

        result = RunResult(exit_code, stdout.getvalue(), stderr.getvalue(), exception)

        if strict and result.exit_code != 0:
            raise RuntimeError(
                f"Call command {args} failed({result.exit_code}): {result.stderr}"
            )
        return result

    return caller


BACKENDS = ["virtualenv", "venv"]


@pytest.fixture(params=BACKENDS)
def venv_backends(project, request):
    project.project_config["venv.backend"] = request.param
    project.project_config["python.use_venv"] = True
    shutil.rmtree(project.root / "__pypackages__", ignore_errors=True)
