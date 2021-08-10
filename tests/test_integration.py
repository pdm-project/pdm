import pytest

from pdm.utils import cd


@pytest.mark.integration
@pytest.mark.parametrize("python_version", ["2.7", "3.6", "3.7", "3.8", "3.9"])
def test_basic_integration(python_version, project_no_init, invoke):
    """An e2e test case to ensure PDM works on all supported Python versions"""
    project = project_no_init
    project.root.joinpath("foo.py").write_text("import django\n")
    invoke(["init"], input="\ny\n\n\n\n\n\n>=2.7\n", obj=project, strict=True)
    invoke(["use", "-f", python_version], obj=project, strict=True)
    project._environment = None
    invoke(["add", "django"], obj=project, strict=True)
    with cd(project.root):
        invoke(["run", "python", "foo.py"], obj=project, strict=True)
        if python_version != "2.7":
            invoke(["build", "-v"], obj=project, strict=True)
    invoke(["remove", "-v", "django"], obj=project, strict=True)
    result = invoke(["list"], obj=project, strict=True)
    assert not any(
        line.strip().lower().startswith("django") for line in result.output.splitlines()
    )
