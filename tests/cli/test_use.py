import os
import shutil
import sys
from pathlib import Path

import pytest

from pdm.cli import actions
from pdm.exceptions import InvalidPyVersion


def test_use_command(project, invoke):
    python_path = Path(shutil.which("python")).as_posix()
    result = invoke(["use", "-f", "python"], obj=project)
    assert result.exit_code == 0
    config_content = project.root.joinpath(".pdm.toml").read_text()
    assert python_path in config_content

    result = invoke(["use", "-f", python_path], obj=project)
    assert result.exit_code == 0

    project.meta["requires-python"] = ">=3.6"
    project.write_pyproject()
    result = invoke(["use", "2.7"], obj=project)
    assert result.exit_code == 1


def test_use_python_by_version(project, invoke):
    python_version = ".".join(map(str, sys.version_info[:2]))
    result = invoke(["use", "-f", python_version], obj=project)
    assert result.exit_code == 0


@pytest.mark.skipif(os.name != "posix", reason="Run on POSIX platforms only")
def test_use_wrapper_python(project):
    wrapper_script = """#!/bin/bash
exec "{}" "$@"
""".format(
        sys.executable
    )
    shim_path = project.root.joinpath("python_shim.sh")
    shim_path.write_text(wrapper_script)
    shim_path.chmod(0o755)

    actions.do_use(project, shim_path.as_posix())
    assert project.python.executable == sys.executable


@pytest.mark.skipif(os.name != "posix", reason="Run on POSIX platforms only")
def test_use_invalid_wrapper_python(project):
    wrapper_script = """#!/bin/bash
echo hello
"""
    shim_path = project.root.joinpath("python_shim.sh")
    shim_path.write_text(wrapper_script)
    shim_path.chmod(0o755)
    with pytest.raises(InvalidPyVersion):
        actions.do_use(project, shim_path.as_posix())
