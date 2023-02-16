"""
Some reusable fixtures for `pytest`.

_New in version 2.4.0_

To enable them in your test, add `pdm.pytest` as a plugin.
You can do so in your root `conftest.py`:

```python title="conftest.py"
# single plugin
pytest_plugins = "pytest.plugin"

# many plugins
pytest_plugins = [
    ...
    "pdm.pytest",
    ...
]
```
"""
from __future__ import annotations

import collections
import json
import os
import shutil
import sys
from dataclasses import dataclass
from io import BufferedReader, BytesIO, StringIO
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    BinaryIO,
    Callable,
    Dict,
    Iterable,
    Iterator,
    Mapping,
    Tuple,
    Union,
    cast,
)
from urllib.parse import urlparse

import pytest
import requests
from packaging.version import parse as parse_version
from pytest_mock import MockerFixture
from unearth import Link

from pdm.cli.actions import do_init
from pdm.cli.hooks import HookManager
from pdm.compat import Protocol
from pdm.core import Core
from pdm.exceptions import CandidateInfoNotFound
from pdm.installers.installers import install_wheel
from pdm.models.backends import get_backend
from pdm.models.candidates import Candidate
from pdm.models.environment import Environment, PrefixEnvironment
from pdm.models.repositories import BaseRepository
from pdm.models.requirements import (
    Requirement,
    filter_requirements_with_extras,
    parse_requirement,
)
from pdm.models.session import PDMSession
from pdm.project.config import Config
from pdm.project.core import Project
from pdm.utils import find_python_in_path, normalize_name, path_to_url

if TYPE_CHECKING:
    from _pytest.fixtures import SubRequest

    from pdm._types import CandidateInfo, Source


class LocalFileAdapter(requests.adapters.BaseAdapter):
    """
    A local file adapter for request.

    Allows to mock some HTTP requests with some local files
    """

    def __init__(
        self,
        aliases: dict[str, Path],
        overrides: dict | None = None,
        strip_suffix: bool = False,
    ):
        super().__init__()
        self.aliases = sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True)
        self.overrides = overrides if overrides is not None else {}
        self.strip_suffix = strip_suffix
        self._opened_files: list[BytesIO | BufferedReader | BinaryIO] = []

    def get_file_path(self, path: str) -> Path | None:
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
        self,
        request: requests.PreparedRequest,
        stream: bool = False,
        timeout: float | tuple[float, float] | tuple[float, None] | None = None,
        verify: bool | str = True,
        cert: str | bytes | tuple[bytes | str, str | bytes] | None = None,
        proxies: Mapping[str, str] | None = None,
    ) -> requests.models.Response:
        request_path = str(urlparse(request.url).path)
        file_path = self.get_file_path(request_path)
        response = requests.models.Response()
        response.url = request.url or ""
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

    def close(self) -> None:
        for fp in self._opened_files:
            fp.close()
        self._opened_files.clear()


class _FakeLink:
    is_wheel = False


class TestRepository(BaseRepository):
    """
    A mock repository to ease testing dependencies
    """

    def __init__(self, sources: list[Source], environment: Environment, pypi_json: Path):
        super().__init__(sources, environment)
        self._pypi_data: dict[str, Any] = {}
        self._pypi_json = pypi_json
        self.load_fixtures()

    def get_raw_dependencies(self, candidate: Candidate) -> list[str]:
        try:
            pypi_data = self._pypi_data[cast(str, candidate.req.key)][cast(str, candidate.version)]
        except KeyError:
            return candidate.prepare(self.environment).metadata.requires or []
        else:
            return pypi_data.get("dependencies", [])

    def add_candidate(self, name: str, version: str, requires_python: str = "") -> None:
        pypi_data = self._pypi_data.setdefault(normalize_name(name), {}).setdefault(version, {})
        pypi_data["requires_python"] = requires_python

    def add_dependencies(self, name: str, version: str, requirements: list[str]) -> None:
        pypi_data = self._pypi_data[normalize_name(name)][version]
        pypi_data.setdefault("dependencies", []).extend(requirements)

    def _get_dependencies_from_fixture(self, candidate: Candidate) -> tuple[list[str], str, str]:
        try:
            pypi_data = self._pypi_data[cast(str, candidate.req.key)][cast(str, candidate.version)]
        except KeyError:
            raise CandidateInfoNotFound(candidate) from None
        deps = pypi_data.get("dependencies", [])
        deps = filter_requirements_with_extras(cast(str, candidate.req.name), deps, candidate.req.extras or ())
        return deps, pypi_data.get("requires_python", ""), ""

    def dependency_generators(self) -> Iterable[Callable[[Candidate], CandidateInfo]]:
        return (
            self._get_dependencies_from_cache,
            self._get_dependencies_from_fixture,
            self._get_dependencies_from_metadata,
        )

    def get_hashes(self, candidate: Candidate) -> dict[Link, str] | None:
        return {}

    def _find_candidates(self, requirement: Requirement) -> Iterable[Candidate]:
        for version, candidate in sorted(
            self._pypi_data.get(cast(str, requirement.key), {}).items(),
            key=lambda item: parse_version(item[0]),
            reverse=True,
        ):
            c = Candidate(
                requirement,
                name=requirement.project_name,
                version=version,
            )
            c.requires_python = candidate.get("requires_python", "")
            c.link = cast(Link, _FakeLink())
            yield c

    def load_fixtures(self) -> None:
        self._pypi_data = json.loads(self._pypi_json.read_text())


class Metadata(dict):
    def get_all(self, name: str, fallback: list[str] | None = None) -> list[str] | None:
        return [self[name]] if name in self else fallback

    def __getitem__(self, __key: str) -> str:
        return cast(str, dict.get(self, __key))


class Distribution:
    """A mock Distribution"""

    def __init__(
        self,
        key: str,
        version: str,
        editable: bool = False,
        metadata: Metadata | None = None,
    ):
        self.version = version
        self.link_file = "editable" if editable else None
        self.dependencies: list[str] = []
        self._metadata = {"Name": key, "Version": version}
        if metadata:
            self._metadata.update(metadata)
        self.name = key

    @property
    def metadata(self) -> Metadata:
        return Metadata(self._metadata)

    def as_req(self) -> Requirement:
        return parse_requirement(f"{self.name}=={self.version}")

    @property
    def requires(self) -> list[str]:
        return self.dependencies

    def read_text(self, path: Path | str) -> None:
        return None


class MockWorkingSet(collections.abc.MutableMapping):
    """A mock working set"""

    _data: dict[str, Distribution]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._data = {}

    def add_distribution(self, dist: Distribution) -> None:
        self._data[dist.name] = dist

    def __getitem__(self, key: str) -> Distribution:
        return self._data[key]

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __setitem__(self, key: str, value: Distribution) -> None:
        self._data[key] = value

    def __delitem__(self, key: str) -> None:
        del self._data[key]


# Note:
#   When going through pytest assertions rewrite, the future annotations is ignored.
#   As a consequence, type definition must comply with Python 3.7 syntax

IndexMap = Dict[str, Path]
"""Path some root-relative http paths to some local paths"""
IndexOverrides = Dict[str, str]
"""PyPI indexes overrides fixture format"""
IndexesDefinition = Dict[str, Union[Tuple[IndexMap, IndexOverrides, bool], IndexMap]]
"""Mock PyPI indexes format"""


@pytest.fixture(scope="session")
def build_env_wheels() -> Iterable[Path]:
    """
    Expose some wheels to be installed in the build environment.

    Override to provide your owns.

    Returns:
        a list of wheels paths to install
    """
    return []


@pytest.fixture(scope="session")
def build_env(build_env_wheels: Iterable[Path], tmp_path_factory: pytest.TempPathFactory) -> Path:
    """
    A fixture build environment

    Args:
        build_env_wheels: a list of wheel to install in the environment

    Returns:
        The build environment temporary path
    """
    d = tmp_path_factory.mktemp("pdm-test-env")
    p = Core().create_project(d)
    env = PrefixEnvironment(p, str(d))
    for wheel in build_env_wheels:
        install_wheel(str(wheel), env)
    return d


@pytest.fixture
def pypi_indexes() -> IndexesDefinition:
    """
    Provides some mocked PyPI entries

    Returns:
        a definition of the mocked indexes
    """
    return {}


@pytest.fixture
def pdm_session(pypi_indexes: IndexesDefinition) -> Callable[[Any], PDMSession]:
    def get_pypi_session(*args: Any, **kwargs: Any) -> PDMSession:
        session = PDMSession(*args, **kwargs)
        for root, specs in pypi_indexes.items():
            index, overrides, strip = specs if isinstance(specs, tuple) else (specs, None, False)
            session.mount(root, LocalFileAdapter(index, overrides=overrides, strip_suffix=strip))
        return session

    return get_pypi_session


def remove_pep582_path_from_pythonpath(pythonpath: str) -> str:
    """Remove all pep582 paths of PDM from PYTHONPATH"""
    paths = pythonpath.split(os.pathsep)
    paths = [path for path in paths if "pdm/pep582" not in path]
    return os.pathsep.join(paths)


@pytest.fixture
def core() -> Iterator[Core]:
    old_config_map = Config._config_map.copy()
    # Turn off use_venv by default, for testing
    Config._config_map["python.use_venv"].default = False
    main = Core()
    yield main
    # Restore the config items
    Config._config_map = old_config_map


@pytest.fixture
def project_no_init(
    tmp_path: Path,
    mocker: MockerFixture,
    core: Core,
    pdm_session: type[PDMSession],
    monkeypatch: pytest.MonkeyPatch,
    build_env: Path,
) -> Project:
    """
    A fixture creating a non-initialized test project for the current test.

    Returns:
        The non-initialized project
    """
    test_home = tmp_path / ".pdm-home"
    test_home.mkdir(parents=True)
    test_home.joinpath("config.toml").write_text(
        '[global_project]\npath = "{}"\n'.format(test_home.joinpath("global-project").as_posix())
    )
    p = core.create_project(tmp_path, global_config=test_home.joinpath("config.toml").as_posix())
    p.global_config["venv.location"] = str(tmp_path / "venvs")
    mocker.patch("pdm.models.environment.PDMSession", pdm_session)
    mocker.patch("pdm.builders.base.EnvBuilder.get_shared_env", return_value=str(build_env))
    tmp_path.joinpath("caches").mkdir(parents=True)
    p.global_config["cache_dir"] = tmp_path.joinpath("caches").as_posix()
    python_path = find_python_in_path(sys.base_prefix)
    if python_path is None:
        raise ValueError("Unable to find a Python path")
    p.project_config["python.path"] = python_path.as_posix()
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.delenv("CONDA_PREFIX", raising=False)
    monkeypatch.delenv("PEP582_PACKAGES", raising=False)
    monkeypatch.delenv("NO_SITE_PACKAGES", raising=False)
    pythonpath = os.getenv("PYTHONPATH", "")
    pythonpath = remove_pep582_path_from_pythonpath(pythonpath)
    if pythonpath:
        monkeypatch.setenv("PYTHONPATH", pythonpath)
    return p


@pytest.fixture
def project(project_no_init: Project) -> Project:
    """
    A fixture creating an initialized test project for the current test.

    Returns:
        The initialized project
    """
    hooks = HookManager(project_no_init, ["post_init"])
    do_init(
        project_no_init,
        "test_project",
        "0.0.0",
        hooks=hooks,
        build_backend=get_backend("pdm-pep517"),
    )
    # Clean the cached property
    project_no_init._environment = None
    return project_no_init


@pytest.fixture
def working_set(mocker: MockerFixture, repository: TestRepository) -> MockWorkingSet:
    """
    a mock working set as a fixture

    Returns:
        a mock working set
    """
    rv = MockWorkingSet()
    mocker.patch.object(Environment, "get_working_set", return_value=rv)

    def install(candidate: Candidate) -> None:
        key = normalize_name(candidate.name or "")
        dist = Distribution(key, cast(str, candidate.version), candidate.req.editable)
        dist.dependencies = repository.get_raw_dependencies(candidate)
        rv.add_distribution(dist)

    def uninstall(dist: Distribution) -> None:
        del rv[dist.name]

    install_manager = mocker.MagicMock()
    install_manager.install.side_effect = install
    install_manager.uninstall.side_effect = uninstall
    mocker.patch("pdm.installers.Synchronizer.get_manager", return_value=install_manager)

    return rv


@pytest.fixture
def local_finder_artifacts() -> Path:
    """
    The local finder search path as a fixture

    Override to provides your own artifacts.

    Returns:
        The path to the artifacts root
    """
    return Path()


@pytest.fixture
def local_finder(project_no_init: Project, local_finder_artifacts: Path) -> None:
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


@pytest.fixture
def repository_pypi_json() -> Path:
    """
    The test repository fake PyPI definition path as a fixture

    Override to provides your own definition path.

    Returns:
        The path to a fake PyPI repository JSON definition
    """
    return Path()


@pytest.fixture()
def repository(
    project: Project,
    mocker: MockerFixture,
    repository_pypi_json: Path,
    local_finder: type[None],
) -> TestRepository:
    """
    A fixture providing a mock PyPI repository

    Returns:
        A mock repository
    """
    rv = TestRepository([], project.environment, repository_pypi_json)
    mocker.patch.object(project, "get_repository", return_value=rv)
    return rv


@dataclass
class RunResult:
    """
    Store a command execution result.
    """

    exit_code: int
    """The execution exit code"""
    stdout: str
    """The execution `stdout` output"""
    stderr: str
    """The execution `stderr` output"""
    exception: Exception | None = None
    """If set, the exception raised on execution"""

    @property
    def output(self) -> str:
        """The execution `stdout` output (`stdout` alias)"""
        return self.stdout

    @property
    def outputs(self) -> str:
        """The execution `stdout` and `stderr` outputs concatenated"""
        return self.stdout + self.stderr

    def print(self) -> None:
        """A debugging facility"""
        print("# exit code:", self.exit_code)
        print("# stdout:", self.stdout, sep="\n")
        print("# stderr:", self.stderr, sep="\n")


class PDMCallable(Protocol):
    """The PDM fixture callable signature"""

    def __call__(
        self,
        args: str | list[str],
        strict: bool = False,
        input: str | None = None,
        obj: Project | None = None,
        env: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> RunResult:
        """
        Args:
            args: the command arguments as a single lexable string or a strings array
            strict: raise an exception on failure instead of returning if enabled
            input: an optional string to be submitted too `stdin`
            obj: an optional existing `Project`.
            env: override the environment variables with those

        Returns:
            The command result
        """
        ...


@pytest.fixture
def pdm(core: Core, monkeypatch: pytest.MonkeyPatch) -> PDMCallable:
    """
    A fixture alloowing to execute PDM commands

    Returns:
        A `pdm` fixture command.
    """
    # Hide the spinner text from testing output to not break existing tests
    monkeypatch.setattr("pdm.termui.DummySpinner._show", lambda self: None)

    def caller(
        args: str | list[str],
        strict: bool = False,
        input: str | None = None,
        obj: Project | None = None,
        env: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> RunResult:
        __tracebackhide__ = True

        stdin = StringIO(input)
        stdout = StringIO()
        stderr = StringIO()
        exit_code: int = 0
        exception: Exception | None = None
        args = args.split() if isinstance(args, str) else args

        with monkeypatch.context() as m:
            m.setattr("sys.stdin", stdin)
            m.setattr("sys.stdout", stdout)
            m.setattr("sys.stderr", stderr)
            for key, value in (env or {}).items():
                m.setenv(key, value)
            try:
                core.main(args, "pdm", obj=obj, **kwargs)
            except SystemExit as e:
                exit_code = cast(int, e.code)
            except Exception as e:
                exit_code = 1
                exception = e

        result = RunResult(exit_code, stdout.getvalue(), stderr.getvalue(), exception)

        if strict and result.exit_code != 0:
            raise RuntimeError(f"Call command {args} failed({result.exit_code}): {result.stderr}")
        return result

    return caller


VENV_BACKENDS = ["virtualenv", "venv"]


@pytest.fixture(params=VENV_BACKENDS)
def venv_backends(project: Project, request: SubRequest) -> None:
    """A fixture iterating over `venv` backends"""
    project.project_config["venv.backend"] = request.param
    project.project_config["venv.prompt"] = "{project_name}-{python_version}"
    project.project_config["python.use_venv"] = True
    shutil.rmtree(project.root / "__pypackages__", ignore_errors=True)
