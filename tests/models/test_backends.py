import shutil
from pathlib import Path

import pytest

from pdm.models.backends import _BACKENDS, get_backend, get_relative_path
from pdm.project import Project
from pdm.utils import cd, path_to_url
from tests import FIXTURES


def _setup_backend(project: Project, backend: str):
    project.pyproject.metadata["requires-python"] = ">=3.6"
    backend_cls = get_backend(backend)
    project.pyproject.build_system.update(backend_cls.build_system())
    project.root.joinpath("test_project").mkdir()
    project.root.joinpath("test_project/__init__.py").touch()
    if backend == "setuptools":
        project.pyproject._data.setdefault("tool", {}).setdefault("setuptools", {}).update(packages=["test_project"])
    elif backend == "hatchling":
        project.pyproject._data.setdefault("tool", {}).setdefault("hatch", {}).setdefault("metadata", {}).update(
            {"allow-direct-references": True}
        )
    project.pyproject.write()
    project._environment = None
    assert isinstance(project.backend, backend_cls)


@pytest.mark.parametrize("backend", _BACKENDS.keys())
def test_project_backend(project, working_set, backend, invoke):
    _setup_backend(project, backend)
    shutil.copytree(FIXTURES / "projects/demo", project.root / "demo")
    project.root.joinpath("sub").mkdir()
    with cd(project.root.joinpath("sub")):
        invoke(["add", "--no-self", "../demo"], obj=project, strict=True)
        assert "idna" in working_set
        assert "demo" in working_set
        dep = project.pyproject.metadata["dependencies"][0]
        demo_path = project.root.joinpath("demo").as_posix()
        demo_url = path_to_url(demo_path)
        if backend in ("pdm-pep517", "pdm-backend"):
            assert dep == "demo @ file:///${PROJECT_ROOT}/demo"
        elif backend == "hatchling":
            assert dep == "demo @ {root:uri}/demo"
        else:
            assert dep == f"demo @ {demo_url}"
        assert project.backend.expand_line(dep) == f"demo @ {demo_url}"
        if backend not in ("hatchling", "pdm-backend"):
            candidate = project.make_self_candidate()
            # We skip hatchling here to avoid installing hatchling into the build env
            metadata_dependency = candidate.prepare(project.environment).metadata.requires[0]
            assert metadata_dependency == f"demo @ {demo_url}"


def test_hatch_expand_variables(monkeypatch):
    root = Path().absolute()
    root_url = path_to_url(root.as_posix())
    backend = get_backend("hatchling")(root)
    monkeypatch.setenv("BAR", "bar")
    assert backend.expand_line("demo @ {root:uri}/demo") == f"demo @ {root_url}/demo"
    assert backend.expand_line("demo=={env:FOO:{env:BAR}}") == "demo==bar"
    assert backend.relative_path_to_url("demo package") == "{root:uri}/demo%20package"
    assert backend.relative_path_to_url("../demo") == "{root:uri}/../demo"


def test_pdm_pep517_expand_variables(monkeypatch):
    root = Path().absolute()
    root_url = path_to_url(root.as_posix())
    backend = get_backend("pdm-pep517")(root)
    monkeypatch.setenv("BAR", "bar")
    assert backend.expand_line("demo @ file:///${PROJECT_ROOT}/demo") == f"demo @ {root_url}/demo"
    assert backend.expand_line("demo==${BAR}") == "demo==bar"
    assert backend.relative_path_to_url("demo package") == "file:///${PROJECT_ROOT}/demo%20package"
    assert backend.relative_path_to_url("../demo") == "file:///${PROJECT_ROOT}/../demo"


@pytest.mark.parametrize(
    "url,path",
    [
        ("file:///foo/bar", None),
        ("https://example.org", None),
        ("file:///${PROJECT_ROOT}/demo%20package", "demo package"),
        ("file:///${PROJECT_ROOT}/../demo", "../demo"),
        ("{root:uri}/demo%20package", "demo package"),
    ],
)
def test_get_relative_path(url, path):
    assert get_relative_path(url) == path
