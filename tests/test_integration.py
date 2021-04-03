import os

import pytest


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
    print(os.getenv("PATH"))
    strict_invoke(["init", "-n"], obj=project)
    strict_invoke(["use", "-f", python_version], obj=project)
    project._environment = None
    strict_invoke(["add", "flask"], obj=project)
    strict_invoke(["run", "flask", "--help"], obj=project)
    strict_invoke(["remove", "flask"], obj=project)
    result = strict_invoke(["list"], obj=project)
    assert not any(
        line.strip().lower().startswith("flask")
        or line.strip().lower().startswith("werkzeug")
        for line in result.output.splitlines()
    )
