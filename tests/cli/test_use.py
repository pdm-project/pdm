import os
import shutil
import sys
from pathlib import Path

import pytest

from pdm.cli.commands.use import Command as UseCommand
from pdm.exceptions import NoPythonVersion
from pdm.models.caches import JSONFileCache


def test_use_command(project, pdm):
    python = "python" if os.name == "nt" else "python3"
    python_path = shutil.which(python)
    result = pdm(["use", "-f", python], obj=project)
    assert result.exit_code == 0
    config_content = project.root.joinpath(".pdm-python").read_text()
    assert Path(python_path).as_posix() in config_content

    result = pdm(["use", "-f", python_path], obj=project)
    assert result.exit_code == 0
    project.pyproject.metadata["requires-python"] = ">=3.6"
    result = pdm(["use", "2.7"], obj=project)
    assert result.exit_code == 1


def test_use_python_by_version(project, pdm):
    python_version = ".".join(map(str, sys.version_info[:2]))
    result = pdm(["use", "-f", python_version], obj=project)
    assert result.exit_code == 0


@pytest.mark.skipif(os.name != "posix", reason="Run on POSIX platforms only")
def test_use_wrapper_python(project):
    wrapper_script = f"""#!/bin/bash
exec "{sys.executable}" "$@"
"""
    shim_path = project.root.joinpath("python_shim.sh")
    shim_path.write_text(wrapper_script)
    shim_path.chmod(0o755)

    UseCommand().do_use(project, shim_path.as_posix())
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
        UseCommand().do_use(project, shim_path.as_posix())


def test_use_remember_last_selection(project, mocker):
    (project.cache_dir / "use_cache.json").unlink(missing_ok=True)
    cache = JSONFileCache(project.cache_dir / "use_cache.json")
    do_use = UseCommand().do_use
    do_use(project, first=True)
    cache._read_cache()
    assert not cache._cache
    do_use(project, "3", first=True)
    cache._read_cache()
    assert "3" in cache
    mocker.patch.object(project, "find_interpreters")
    do_use(project, "3")
    project.find_interpreters.assert_not_called()


def test_use_venv_python(project, pdm):
    pdm(["venv", "create"], obj=project, strict=True)
    pdm(["venv", "create", "--name", "test"], obj=project, strict=True)
    project.global_config["python.use_venv"] = True
    venv_location = project.config["venv.location"]
    do_use = UseCommand().do_use
    do_use(project, venv="in-project")
    assert project.python.executable.parent.parent == project.root.joinpath(".venv")
    do_use(project, venv="test")
    assert project.python.executable.parent.parent.parent == Path(venv_location)
    with pytest.raises(Exception, match="No virtualenv with key 'non-exists' is found"):
        do_use(project, venv="non-exists")


def test_use_auto_install_and_no_auto_install_are_mutual_exclusive(project, pdm):
    command = ["use", "--auto-install-min", "-f"]
    with pytest.raises(RuntimeError) as error:
        result = pdm(command, obj=project, strict=True)
        assert str(error.value).startswith(f"Call command {command} failed")
        assert result.exit_code != 0

    command = ["use", "--auto-install-max", "-f"]
    with pytest.raises(RuntimeError) as error:
        result = pdm(command, obj=project, strict=True)
        assert str(error.value).startswith(f"Call command {command} failed")
        assert result.exit_code != 0

    command = ["use", "--auto-install-max", "--auto-install-min"]
    with pytest.raises(RuntimeError) as error:
        result = pdm(command, obj=project, strict=True)
        assert str(error.value).startswith(f"Call command {command} failed")
        assert result.exit_code != 0
