import pytest

from pdm.utils import cd


@pytest.fixture
def strict_invoke(invoke):
    def new_invoke(args, **kwargs):
        result = invoke(args, **kwargs)
        if result.exit_code != 0:
            raise RuntimeError(f"Call command {args} fail: {result.stderr}")
        return result

    return new_invoke


@pytest.mark.integration
@pytest.mark.parametrize("python_version", ["2.7", "3.6", "3.7", "3.8", "3.9"])
def test_basic_integration(python_version, project_no_init, strict_invoke):
    """An e2e test case to ensure PDM works on all supported Python versions"""
    project = project_no_init
    project.root.joinpath("foo.py").write_text("import django\n")
    strict_invoke(["init"], input="\ny\n\n\n\n\n\n>=2.7\n", obj=project)
    strict_invoke(["use", "-f", python_version], obj=project)
    project._environment = None
    strict_invoke(["add", "django"], obj=project)
    with cd(project.root):
        strict_invoke(["run", "python", "foo.py"], obj=project)
        if python_version != "2.7":
            strict_invoke(["build", "-v"], obj=project)
    strict_invoke(["remove", "django"], obj=project)
    result = strict_invoke(["list"], obj=project)
    assert not any(
        line.strip().lower().startswith("django") for line in result.output.splitlines()
    )
