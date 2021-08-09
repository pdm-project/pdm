import pytest

from pdm.models.specifiers import PySpecSet


@pytest.mark.usefixtures("repository")
def test_deprecated_section_argument(project, invoke, working_set):
    project.environment.python_requires = PySpecSet(">=3.6")
    r = invoke(["add", "--section", "optional", "demo"], obj=project)
    assert r.exit_code == 0
    assert "DEPRECATED" in r.stderr

    assert "demo" in working_set
    assert "demo" in project.get_dependencies("optional")
