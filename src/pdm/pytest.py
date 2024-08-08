"""
Some reusable fixtures for `pytest`.

+++ 2.4.0

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

import collections.abc
import json
import os
import shutil
import sys
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Generator,
    Iterable,
    Iterator,
    Mapping,
    MutableMapping,
    Tuple,
    Union,
    cast,
)

import httpx
import pytest
from httpx._content import IteratorByteStream
from pytest_mock import MockerFixture
from unearth import Link

from pdm.core import Core
from pdm.environments import BaseEnvironment, PythonEnvironment
from pdm.exceptions import CandidateInfoNotFound
from pdm.installers.installers import install_wheel
from pdm.models.backends import DEFAULT_BACKEND
from pdm.models.candidates import Candidate
from pdm.models.repositories import BaseRepository, CandidateMetadata
from pdm.models.requirements import (
    Requirement,
    filter_requirements_with_extras,
    parse_requirement,
)
from pdm.models.session import PDMPyPIClient
from pdm.project.config import Config
from pdm.project.core import Project
from pdm.utils import find_python_in_path, normalize_name, parse_version, path_to_url

if TYPE_CHECKING:
    from typing import Protocol

    from _pytest.fixtures import SubRequest

    from pdm._types import FileHash


class FileByteStream(IteratorByteStream):
    def close(self) -> None:
        self._stream.close()  # type: ignore[attr-defined]


class LocalIndexTransport(httpx.BaseTransport):
    """
    A local file transport for HTTPX.

    Allows to mock some HTTP requests with some local files
    """

    def __init__(
        self,
        aliases: dict[str, Path],
        overrides: IndexOverrides | None = None,
        strip_suffix: bool = False,
    ):
        super().__init__()
        self.aliases = sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True)
        self.overrides = overrides if overrides is not None else {}
        self.strip_suffix = strip_suffix

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

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        request_path = request.url.path
        file_path = self.get_file_path(request_path)
        headers: dict[str, str] = {}
        stream: httpx.SyncByteStream | None = None
        content: bytes | None = None
        if request_path in self.overrides:
            status_code = 200
            content = self.overrides[request_path]
            headers["Content-Type"] = "text/html"
        elif file_path is None or not file_path.exists():
            status_code = 404
        else:
            status_code = 200
            stream = FileByteStream(file_path.open("rb"))
            if file_path.suffix == ".html":
                headers["Content-Type"] = "text/html"
            elif file_path.suffix == ".json":
                headers["Content-Type"] = "application/vnd.pypi.simple.v1+json"
        return httpx.Response(status_code, headers=headers, content=content, stream=stream)


class RepositoryData:
    def __init__(self, pypi_json: Path) -> None:
        self.pypi_data = self.load_fixtures(pypi_json)

    @staticmethod
    def load_fixtures(pypi_json: Path) -> dict[str, Any]:
        return json.loads(pypi_json.read_text())

    def add_candidate(self, name: str, version: str, requires_python: str = "") -> None:
        pypi_data = self.pypi_data.setdefault(normalize_name(name), {}).setdefault(version, {})
        pypi_data["requires_python"] = requires_python

    def add_dependencies(self, name: str, version: str, requirements: list[str]) -> None:
        pypi_data = self.pypi_data[normalize_name(name)][version]
        pypi_data.setdefault("dependencies", []).extend(requirements)

    def get_raw_dependencies(self, candidate: Candidate) -> tuple[str, list[str]]:
        try:
            pypi_data = self.pypi_data[cast(str, candidate.req.key)]
            for version, data in sorted(pypi_data.items(), key=lambda item: len(item[0])):
                base, *_ = version.partition("+")
                if candidate.version in (version, base):
                    return version, data.get("dependencies", [])
        except KeyError:
            pass
        assert candidate.prepared is not None
        meta = candidate.prepared.metadata
        return meta.version, meta.requires or []


class TestRepository(BaseRepository):
    """
    A mock repository to ease testing dependencies
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._pypi_data = self.get_data()

    def get_data(self) -> dict[str, Any]:
        raise NotImplementedError("To be injected by the fixture.")

    def _get_dependencies_from_fixture(self, candidate: Candidate) -> CandidateMetadata:
        try:
            pypi_data = self._pypi_data[cast(str, candidate.req.key)][cast(str, candidate.version)]
        except KeyError:
            raise CandidateInfoNotFound(candidate) from None
        deps = pypi_data.get("dependencies", [])
        deps = filter_requirements_with_extras(deps, candidate.req.extras or ())
        return CandidateMetadata(deps, pypi_data.get("requires_python", ""), "")

    def dependency_generators(self) -> Iterable[Callable[[Candidate], CandidateMetadata]]:
        return (
            self._get_dependencies_from_cache,
            self._get_dependencies_from_local_package,
            self._get_dependencies_from_fixture,
            self._get_dependencies_from_metadata,
        )

    def get_hashes(self, candidate: Candidate) -> list[FileHash]:
        return []

    def _find_candidates(self, requirement: Requirement, minimal_version: bool) -> Iterable[Candidate]:
        for version, candidate in sorted(
            self._pypi_data.get(cast(str, requirement.key), {}).items(),
            key=lambda item: parse_version(item[0]),
            reverse=not minimal_version,
        ):
            c = Candidate(
                requirement,
                name=requirement.project_name,
                version=version,
            )
            c.requires_python = candidate.get("requires_python", "")
            c.link = Link(f"https://mypypi.org/packages/{c.name}-{c.version}.tar.gz")
            yield c


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

    def is_owned(self, key: str) -> bool:
        return key in self._data

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
IndexOverrides = Dict[str, bytes]
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


@pytest.fixture(autouse=True)
def temp_env() -> Generator[MutableMapping[str, str]]:
    old_env = os.environ.copy()
    try:
        yield os.environ
    finally:
        os.environ.clear()
        os.environ.update(old_env)


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
    env = PythonEnvironment(p, prefix=str(d), python=sys.executable)
    for wheel in build_env_wheels:
        install_wheel(wheel, env)
    return d


@pytest.fixture
def pypi_indexes() -> IndexesDefinition:
    """
    Provides some mocked PyPI entries

    Returns:
        a definition of the mocked indexes
    """
    return {}


_build_session = BaseEnvironment._build_session


@pytest.fixture
def build_test_session(pypi_indexes: IndexesDefinition) -> Callable[..., PDMPyPIClient]:
    def get_pypi_session(*args: Any, **kwargs: Any) -> PDMPyPIClient:
        mounts: dict[str, httpx.BaseTransport] = {}
        for root, specs in pypi_indexes.items():
            index, overrides, strip = specs if isinstance(specs, tuple) else (specs, None, False)
            mounts[root] = LocalIndexTransport(index, overrides=overrides, strip_suffix=strip)
        kwargs["mounts"] = mounts
        return _build_session(*args, **kwargs)

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
    with main.exit_stack:
        yield main
    # Restore the config items
    Config._config_map = old_config_map


@pytest.fixture
def project_no_init(
    tmp_path: Path,
    mocker: MockerFixture,
    core: Core,
    build_test_session: Callable[..., PDMPyPIClient],
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
    p.global_config["python.install_root"] = str(tmp_path / "pythons")
    p.global_config["venv.location"] = str(tmp_path / "venvs")
    mocker.patch.object(BaseEnvironment, "_build_session", build_test_session)
    mocker.patch("pdm.builders.base.EnvBuilder.get_shared_env", return_value=str(build_env))
    tmp_path.joinpath("caches").mkdir(parents=True)
    p.global_config["cache_dir"] = tmp_path.joinpath("caches").as_posix()
    p.global_config["log_dir"] = tmp_path.joinpath("logs").as_posix()
    python_path = find_python_in_path(sys.base_prefix)
    if python_path is None:
        raise ValueError("Unable to find a Python path")
    p._saved_python = python_path.as_posix()
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
    from pdm.cli.utils import merge_dictionary

    data = {
        "project": {
            "name": "test-project",
            "version": "0.0.0",
            "description": "",
            "authors": [],
            "license": {"text": "MIT"},
            "dependencies": [],
            "requires-python": ">=3.7",
        },
        "build-system": DEFAULT_BACKEND.build_system(),
    }

    merge_dictionary(project_no_init.pyproject._data, data)
    project_no_init.pyproject.write()
    # Clean the cached property
    project_no_init._environment = None
    return project_no_init


@pytest.fixture
def working_set(mocker: MockerFixture, repository: RepositoryData) -> MockWorkingSet:
    """
    a mock working set as a fixture

    Returns:
        a mock working set
    """
    from pdm.installers import InstallManager

    rv = MockWorkingSet()
    mocker.patch.object(BaseEnvironment, "get_working_set", return_value=rv)

    class MockInstallManager(InstallManager):
        def install(self, candidate: Candidate) -> Distribution:  # type: ignore[override]
            key = normalize_name(candidate.name or "")
            candidate.prepare(self.environment)
            version, dependencies = repository.get_raw_dependencies(candidate)
            dist = Distribution(key, version, candidate.req.editable)
            dist.dependencies = dependencies
            rv.add_distribution(dist)
            return dist

        def uninstall(self, dist: Distribution) -> None:  # type: ignore[override]
            del rv[dist.name]

        def overwrite(self, dist: Distribution, candidate: Candidate) -> None:  # type: ignore[override]
            self.uninstall(dist)
            self.install(candidate)

    mocker.patch.object(Core, "install_manager_class", MockInstallManager)

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
    core: Core,
    mocker: MockerFixture,
    repository_pypi_json: Path,
    local_finder: type[None],
) -> RepositoryData:
    """
    A fixture providing a mock PyPI repository

    Returns:
        A mock repository
    """
    repo = RepositoryData(repository_pypi_json)
    core.repository_class = TestRepository
    mocker.patch.object(TestRepository, "get_data", return_value=repo.pypi_data)
    return repo


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


if TYPE_CHECKING:

    class PDMCallable(Protocol):
        """The PDM fixture callable signature"""

        def __call__(
            self,
            args: str | list[str],
            strict: bool = False,
            input: str | None = None,
            obj: Project | None = None,
            env: Mapping[str, str] | None = None,
            cleanup: bool = True,
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
    A fixture allowing to execute PDM commands

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
        cleanup: bool = True,
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
            old_env = os.environ.copy()
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
            finally:
                os.environ.clear()
                os.environ.update(old_env)
                if cleanup:
                    core.exit_stack.close()

        result = RunResult(exit_code, stdout.getvalue(), stderr.getvalue(), exception)

        if strict and result.exit_code != 0:
            if result.exception:
                raise result.exception.with_traceback(result.exception.__traceback__)
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
