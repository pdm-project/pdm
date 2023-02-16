import sys
from unittest.mock import ANY

import pytest

from pdm.cli import actions
from pdm.models.backends import get_backend
from pdm.models.python import PythonInfo

PYTHON_VERSION = f"{sys.version_info[0]}.{sys.version_info[1]}"


def test_init_validate_python_requires(project_no_init):
    with pytest.raises(ValueError):
        actions.do_init(project_no_init, python_requires="3.7")


def test_init_command(project_no_init, invoke, mocker):
    mocker.patch(
        "pdm.cli.commands.init.get_user_email_from_git",
        return_value=("Testing", "me@example.org"),
    )
    do_init = mocker.patch.object(actions, "do_init")
    invoke(["init"], input="\n\n\n\n\n\n", strict=True, obj=project_no_init)
    python_version = f"{project_no_init.python.major}.{project_no_init.python.minor}"
    do_init.assert_called_with(
        project_no_init,
        name="",
        version="",
        description="",
        license="MIT",
        author="Testing",
        email="me@example.org",
        python_requires=f">={python_version}",
        build_backend=None,
        hooks=ANY,
    )


def test_init_command_library(project_no_init, invoke, mocker):
    mocker.patch(
        "pdm.cli.commands.init.get_user_email_from_git",
        return_value=("Testing", "me@example.org"),
    )
    do_init = mocker.patch.object(actions, "do_init")
    result = invoke(
        ["init"],
        input="\ny\ntest-project\n\nTest Project\n1\n\n\n\n\n",
        obj=project_no_init,
    )
    assert result.exit_code == 0
    python_version = f"{project_no_init.python.major}.{project_no_init.python.minor}"
    do_init.assert_called_with(
        project_no_init,
        name="test-project",
        version="0.1.0",
        description="Test Project",
        license="MIT",
        author="Testing",
        email="me@example.org",
        python_requires=f">={python_version}",
        build_backend=get_backend("setuptools"),
        hooks=ANY,
    )


def test_init_non_interactive(project_no_init, invoke, mocker):
    mocker.patch(
        "pdm.cli.commands.init.get_user_email_from_git",
        return_value=("Testing", "me@example.org"),
    )
    do_init = mocker.patch.object(actions, "do_init")
    do_use = mocker.patch.object(actions, "do_use", return_value=PythonInfo.from_path(sys.executable))
    result = invoke(["init", "-n"], obj=project_no_init)
    assert result.exit_code == 0
    python_version = f"{project_no_init.python.major}.{project_no_init.python.minor}"
    do_use.assert_called_once_with(
        project_no_init,
        ANY,
        first=True,
        ignore_remembered=True,
        ignore_requires_python=True,
        save=False,
        hooks=ANY,
    )
    do_init.assert_called_with(
        project_no_init,
        name="",
        version="",
        description="",
        license="MIT",
        author="Testing",
        email="me@example.org",
        python_requires=f">={python_version}",
        build_backend=None,
        hooks=ANY,
    )


def test_init_auto_create_venv(project_no_init, invoke, mocker):
    mocker.patch("pdm.cli.commands.init.get_venv_like_prefix", return_value=None)
    project_no_init.project_config["python.use_venv"] = True
    result = invoke(["init"], input="\n\n\n\n\n\n\n", obj=project_no_init)
    assert result.exit_code == 0
    assert project_no_init.python.executable.parent.parent == project_no_init.root / ".venv"


def test_init_auto_create_venv_specify_python(project_no_init, invoke, mocker):
    mocker.patch("pdm.cli.commands.init.get_venv_like_prefix", return_value=None)
    project_no_init.project_config["python.use_venv"] = True
    result = invoke(
        ["init", f"--python={PYTHON_VERSION}"],
        input="\n\n\n\n\n\n",
        obj=project_no_init,
    )
    assert result.exit_code == 0
    assert project_no_init.python.executable.parent.parent == project_no_init.root / ".venv"


def test_init_auto_create_venv_answer_no(project_no_init, invoke, mocker):
    mocker.patch("pdm.cli.commands.init.get_venv_like_prefix", return_value=None)
    creator = mocker.patch("pdm.cli.commands.venv.backends.Backend.create")
    project_no_init.project_config["python.use_venv"] = True
    result = invoke(["init"], input="\nn\n\n\n\n\n\n\n", obj=project_no_init)
    assert result.exit_code == 0
    creator.assert_not_called()
    assert project_no_init.python.executable.parent.parent != project_no_init.root / ".venv"
