import sys
from unittest.mock import ANY

from pdm.compat import tomllib
from pdm.models.python import PythonInfo

PYTHON_VERSION = f"{sys.version_info[0]}.{sys.version_info[1]}"


def test_init_validate_python_requires(project_no_init, pdm):
    result = pdm(["init"], input="\n\n\n\n\n3.7\n", obj=project_no_init)
    assert result.exit_code != 0
    assert "InvalidSpecifier" in result.stderr


def test_init_command(project_no_init, pdm, mocker):
    mocker.patch(
        "pdm.cli.commands.init.get_user_email_from_git",
        return_value=("Testing", "me@example.org"),
    )
    pdm(["init"], input="\n\n\n\n\n\n", strict=True, obj=project_no_init)
    python_version = f"{project_no_init.python.major}.{project_no_init.python.minor}"
    data = {
        "project": {
            "authors": [{"email": "me@example.org", "name": "Testing"}],
            "dependencies": [],
            "description": "",
            "license": {"text": "MIT"},
            "name": "",
            "requires-python": f">={python_version}",
            "readme": "README.md",
            "version": "",
        },
        "build-system": {"build-backend": "pdm.backend", "requires": ["pdm-backend"]},
    }

    with open(project_no_init.root.joinpath("pyproject.toml"), "rb") as fp:
        assert tomllib.load(fp) == data


def test_init_command_library(project_no_init, pdm, mocker):
    mocker.patch(
        "pdm.cli.commands.init.get_user_email_from_git",
        return_value=("Testing", "me@example.org"),
    )
    result = pdm(
        ["init"],
        input="\ny\ntest-project\n\nTest Project\n1\n\n\n\n\n",
        obj=project_no_init,
    )
    assert result.exit_code == 0
    python_version = f"{project_no_init.python.major}.{project_no_init.python.minor}"
    data = {
        "project": {
            "authors": [{"email": "me@example.org", "name": "Testing"}],
            "dependencies": [],
            "description": "Test Project",
            "license": {"text": "MIT"},
            "name": "test-project",
            "requires-python": f">={python_version}",
            "readme": "README.md",
            "version": "0.1.0",
        },
        "build-system": {"build-backend": "setuptools.build_meta", "requires": ["setuptools>=61", "wheel"]},
    }

    with open(project_no_init.root.joinpath("pyproject.toml"), "rb") as fp:
        assert tomllib.load(fp) == data


def test_init_non_interactive(project_no_init, pdm, mocker):
    mocker.patch(
        "pdm.cli.commands.init.get_user_email_from_git",
        return_value=("Testing", "me@example.org"),
    )
    do_use = mocker.patch("pdm.cli.commands.use.Command.do_use", return_value=PythonInfo.from_path(sys.executable))
    result = pdm(["init", "-n"], obj=project_no_init)
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
    data = {
        "project": {
            "authors": [{"email": "me@example.org", "name": "Testing"}],
            "dependencies": [],
            "description": "",
            "license": {"text": "MIT"},
            "name": "",
            "requires-python": f">={python_version}",
            "readme": "README.md",
            "version": "",
        },
        "build-system": {"build-backend": "pdm.backend", "requires": ["pdm-backend"]},
    }

    with open(project_no_init.root.joinpath("pyproject.toml"), "rb") as fp:
        assert tomllib.load(fp) == data


def test_init_auto_create_venv(project_no_init, pdm, mocker):
    mocker.patch("pdm.models.python.PythonInfo.get_venv", return_value=None)
    project_no_init.project_config["python.use_venv"] = True
    result = pdm(["init"], input="\n\n\n\n\n\n\n", obj=project_no_init)
    assert result.exit_code == 0
    assert project_no_init.python.executable.parent.parent == project_no_init.root / ".venv"
    assert ".pdm-python" in (project_no_init.root / ".gitignore").read_text()


def test_init_auto_create_venv_specify_python(project_no_init, pdm, mocker):
    mocker.patch("pdm.models.python.PythonInfo.get_venv", return_value=None)
    project_no_init.project_config["python.use_venv"] = True
    result = pdm(
        ["init", f"--python={PYTHON_VERSION}"],
        input="\n\n\n\n\n\n",
        obj=project_no_init,
    )
    assert result.exit_code == 0
    assert project_no_init.python.executable.parent.parent == project_no_init.root / ".venv"


def test_init_auto_create_venv_answer_no(project_no_init, pdm, mocker):
    mocker.patch("pdm.models.python.PythonInfo.get_venv", return_value=None)
    creator = mocker.patch("pdm.cli.commands.venv.backends.Backend.create")
    project_no_init.project_config["python.use_venv"] = True
    result = pdm(["init"], input="\nn\n\n\n\n\n\n\n", obj=project_no_init)
    assert result.exit_code == 0
    creator.assert_not_called()
    assert project_no_init.python.executable.parent.parent != project_no_init.root / ".venv"
