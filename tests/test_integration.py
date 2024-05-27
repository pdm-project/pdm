import findpython
import pytest

from pdm.utils import cd

PYTHON_VERSIONS = ["3.7", "3.8", "3.9", "3.10", "3.11", "3.12", "3.13"]
PYPROJECT = {
    "project": {"name": "test-project", "version": "0.1.0", "requires-python": ">=3.7"},
    "build-system": {"requires": ["pdm-backend"], "build-backend": "pdm.backend"},
}


def get_python_versions():
    finder = findpython.Finder(resolve_symlinks=True)
    available_versions = []
    for version in PYTHON_VERSIONS:
        v = finder.find(version)
        if v and v.is_valid():
            available_versions.append(version)
    return available_versions


@pytest.mark.integration
@pytest.mark.network
@pytest.mark.flaky(reruns=3)
@pytest.mark.parametrize("python_version", get_python_versions())
def test_basic_integration(python_version, core, tmp_path, pdm):
    """An e2e test case to ensure PDM works on all supported Python versions"""
    project = core.create_project(tmp_path)
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


def test_actual_list_freeze(project, local_finder, pdm):
    pdm(["config", "-l", "install.parallel", "false"], obj=project, strict=True)
    pdm(["add", "first"], obj=project, strict=True)
    r = pdm(["list", "--freeze"], obj=project)
    assert "first==2.0.2" in r.output
