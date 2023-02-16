import findpython
import pytest

from pdm.utils import cd

PYTHON_VERSIONS = ["3.6", "3.7", "3.8", "3.9", "3.10", "3.11"]
PYPROJECT = {
    "project": {"name": "test-project", "version": "0.1.0", "requires-python": ">=3.6"},
    "build-system": {"requires": ["pdm-pep517"], "build-backend": "pdm.pep517.api"},
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
def test_basic_integration(python_version, core, tmp_path, invoke):
    """An e2e test case to ensure PDM works on all supported Python versions"""
    project = core.create_project(tmp_path)
    project.pyproject.set_data(PYPROJECT)
    project.root.joinpath("foo.py").write_text("import django\n")
    project._environment = None
    invoke(["use", "-f", python_version], obj=project, strict=True)
    invoke(["add", "django", "-v"], obj=project, strict=True)
    with cd(project.root):
        invoke(["run", "python", "foo.py"], obj=project, strict=True)
        invoke(["build", "-v"], obj=project, strict=True)
    invoke(["remove", "-v", "django"], obj=project, strict=True)
    result = invoke(["list"], obj=project, strict=True)
    assert not any(line.strip().lower().startswith("django") for line in result.output.splitlines())


def test_actual_list_freeze(project, local_finder, invoke):
    invoke(["config", "-l", "install.parallel", "false"], obj=project, strict=True)
    invoke(["add", "first"], obj=project, strict=True)
    r = invoke(["list", "--freeze"], obj=project)
    assert "first==2.0.2" in r.output
