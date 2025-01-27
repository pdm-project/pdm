import findpython
import pytest

from pdm.utils import cd

DEFAULT_PYTHON_VERSIONS = ["3.9", "3.10", "3.11", "3.12", "3.13"]
PYPROJECT = {
    "project": {"name": "test-project", "version": "0.1.0", "requires-python": ">=3.7"},
    "build-system": {"requires": ["pdm-backend"], "build-backend": "pdm.backend"},
}


def get_python_versions():
    finder = findpython.Finder(resolve_symlinks=True)
    available_versions = []
    for version in DEFAULT_PYTHON_VERSIONS:
        v = finder.find(version)
        if v and v.is_valid():
            available_versions.append(version)
    return available_versions


PYTHON_VERSIONS = get_python_versions()


@pytest.mark.integration
@pytest.mark.network
@pytest.mark.flaky(reruns=3)
@pytest.mark.parametrize("python_version", PYTHON_VERSIONS)
def test_basic_integration(python_version, core, tmp_path, pdm):
    """An e2e test case to ensure PDM works on all supported Python versions"""
    project = core.create_project(tmp_path)
    project.project_config["python.use_venv"] = True
    project.pyproject.set_data(PYPROJECT)
    project.root.joinpath("foo.py").write_text("import django\n")
    project._environment = None
    pdm(["use", "-f", python_version], obj=project, strict=True, cleanup=False)
    pdm(["add", "django", "-v"], obj=project, strict=True, cleanup=False)
    with cd(project.root):
        pdm(["run", "python", "foo.py"], obj=project, strict=True, cleanup=False)
        pdm(["build", "-v"], obj=project, strict=True, cleanup=False)
    pdm(["remove", "-v", "django"], obj=project, strict=True, cleanup=False)
    result = pdm(["list"], obj=project, strict=True)
    assert not any(line.strip().lower().startswith("django") for line in result.output.splitlines())


@pytest.mark.integration
@pytest.mark.skipif(len(PYTHON_VERSIONS) < 2, reason="Need at least 2 Python versions to test")
def test_use_python_write_file(pdm, project):
    pdm(["use", PYTHON_VERSIONS[0]], obj=project, strict=True)
    assert f"{project.python.major}.{project.python.minor}" == PYTHON_VERSIONS[0]
    assert project.root.joinpath(".python-version").read_text().strip() == PYTHON_VERSIONS[0]
    pdm(["use", PYTHON_VERSIONS[1]], obj=project, strict=True)
    assert f"{project.python.major}.{project.python.minor}" == PYTHON_VERSIONS[1]
    assert project.root.joinpath(".python-version").read_text().strip() == PYTHON_VERSIONS[1]


@pytest.mark.integration
@pytest.mark.parametrize("python_version", PYTHON_VERSIONS)
@pytest.mark.parametrize("via_env", [True, False])
def test_init_project_respect_version_file(pdm, project, python_version, via_env, monkeypatch):
    project.project_config["python.use_venv"] = True
    if via_env:
        monkeypatch.setenv("PDM_PYTHON_VERSION", python_version)
    else:
        project.root.joinpath(".python-version").write_text(python_version)
    project._saved_python = None
    project._environment = None
    pdm(["install"], obj=project, strict=True)
    assert f"{project.python.major}.{project.python.minor}" == python_version


def test_actual_list_freeze(project, local_finder, pdm):
    pdm(["config", "-l", "install.parallel", "false"], obj=project, strict=True)
    pdm(["add", "first"], obj=project, strict=True)
    r = pdm(["list", "--freeze"], obj=project)
    assert "first==2.0.2" in r.output
