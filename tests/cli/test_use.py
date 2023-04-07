import os
import shutil
import sys
from pathlib import Path

import pytest

from pdm.cli import actions
from pdm.exceptions import NoPythonVersion
from pdm.models.caches import JSONFileCache


def test_use_command(project, invoke):
    python = "python" if os.name == "nt" else "python3"
    python_path = shutil.which(python)
    result = invoke(["use", "-f", python], obj=project)
    assert result.exit_code == 0
    config_content = project.root.joinpath(".pdm-python").read_text()
    assert Path(python_path).as_posix() in config_content

    result = invoke(["use", "-f", python_path], obj=project)
    assert result.exit_code == 0
    project.pyproject.metadata["requires-python"] = ">=3.6"
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
    assert project.python.executable == Path(sys.executable)


@pytest.mark.skipif(os.name != "posix", reason="Run on POSIX platforms only")
def test_use_invalid_wrapper_python(project):
    wrapper_script = """#!/bin/bash
echo hello
"""
    shim_path = project.root.joinpath("python_shim.sh")
    shim_path.write_text(wrapper_script)
    shim_path.chmod(0o755)
    with pytest.raises(NoPythonVersion):
        actions.do_use(project, shim_path.as_posix())


def test_use_remember_last_selection(project, mocker):
    cache = JSONFileCache(project.cache_dir / "use_cache.json")
    cache.clear()
    actions.do_use(project, first=True)
    cache._read_cache()
    assert not cache._cache
    actions.do_use(project, "3", first=True)
    cache._read_cache()
    assert "3" in cache
    mocker.patch.object(project, "find_interpreters")
    actions.do_use(project, "3")
    project.find_interpreters.assert_not_called()


def test_use_venv_python(project, pdm):
    pdm(["venv", "create"], obj=project, strict=True)
    pdm(["venv", "create", "--name", "test"], obj=project, strict=True)
    project.global_config["python.use_venv"] = True
    venv_location = project.config["venv.location"]
    actions.do_use(project, venv="in-project")
    assert project.python.executable.parent.parent == project.root.joinpath(".venv")
    actions.do_use(project, venv="test")
    assert project.python.executable.parent.parent.parent == Path(venv_location)
    with pytest.raises(Exception, match="No virtualenv with key 'non-exists' is found"):
        actions.do_use(project, venv="non-exists")
