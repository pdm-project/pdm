import functools
import os
import shutil

import pytest
from click.testing import CliRunner
from pdm.cli import actions, commands


@pytest.fixture()
def invoke():
    runner = CliRunner()
    return functools.partial(runner.invoke, commands.cli)


def test_help_option(invoke):
    result = invoke(["--help"])
    assert "PDM - Python Development Master" in result.output


def test_lock_command(project, invoke, mocker):
    m = mocker.patch.object(actions, "do_lock")
    invoke(["lock"], obj=project)
    m.assert_called_with(project)


def test_install_command(project, invoke, mocker):
    do_lock = mocker.patch.object(actions, "do_lock")
    do_sync = mocker.patch.object(actions, "do_sync")
    invoke(["install"], obj=project)
    do_lock.assert_called_once()
    do_sync.assert_called_once()


def test_sync_command(project, invoke, mocker):
    do_sync = mocker.patch.object(actions, "do_sync")
    invoke(["sync"], obj=project)
    do_sync.assert_called_once()


def test_update_command(project, invoke, mocker):
    do_update = mocker.patch.object(actions, "do_update")
    invoke(["update"], obj=project)
    do_update.assert_called_once()


def test_remove_command(project, invoke, mocker):
    do_remove = mocker.patch.object(actions, "do_remove")
    invoke(["remove", "demo"], obj=project)
    do_remove.assert_called_once()


def test_add_command(project, invoke, mocker):
    do_add = mocker.patch.object(actions, "do_add")
    invoke(["add", "requests"], obj=project)
    do_add.assert_called_once()


def test_build_command(project, invoke, mocker):
    do_build = mocker.patch.object(actions, "do_build")
    invoke(["build"], obj=project)
    do_build.assert_called_once()


def test_list_command(project, invoke, mocker):
    do_list = mocker.patch.object(actions, "do_list")
    invoke(["list"], obj=project)
    do_list.assert_called_once()


def test_run_command(invoke, capfd):
    result = invoke(["run", "python", "-c", "import halo;print(halo.__file__)"])
    assert result.exit_code == 0
    assert os.sep.join(["pdm", "__pypackages__"]) in capfd.readouterr()[0]


def test_run_command_not_found(invoke):
    result = invoke(["run", "foobar"])
    assert result.exit_code == 2
    assert "Error: Command 'foobar' is not found on your PATH." in result.output


def test_run_pass_exit_code(invoke):
    result = invoke(["run", "python", "-c", "1/0"])
    assert result.exit_code == 1


def test_uncaught_error(invoke, mocker):
    mocker.patch.object(actions, "do_list", side_effect=RuntimeError("test error"))
    result = invoke(["list"])
    assert "RuntimeError: test error" in result.output

    result = invoke(["list", "-v"])
    assert isinstance(result.exception, RuntimeError)


def test_use_command(project, invoke):
    python_path = shutil.which("python")
    result = invoke(["use", "python"], obj=project)
    assert result.exit_code == 0
    config_content = project.root.joinpath(".pdm.toml").read_text()
    assert python_path in config_content

    result = invoke(["use", python_path], obj=project)
    assert result.exit_code == 0

    project.tool_settings["python_requires"] = ">=3.6"
    project.write_pyproject()
    result = invoke(["use", "2.7"], obj=project)
    assert result.exit_code == 1
