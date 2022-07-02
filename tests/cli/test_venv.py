import os
import re
import shutil
import sys
from unittest.mock import ANY

import pytest

from pdm.cli.commands.venv import backends


@pytest.fixture()
def fake_create(monkeypatch):
    def fake_create(self, location, *args):
        location.mkdir(parents=True)

    monkeypatch.setattr(backends.VirtualenvBackend, "perform_create", fake_create)
    monkeypatch.setattr(backends.VenvBackend, "perform_create", fake_create)
    monkeypatch.setattr(backends.CondaBackend, "perform_create", fake_create)


@pytest.mark.usefixtures("fake_create")
def test_venv_create(invoke, project):
    project.project_config["venv.in_project"] = False
    result = invoke(["venv", "create"], obj=project)
    assert result.exit_code == 0, result.stderr
    venv_path = re.match(
        r"Virtualenv (.+) is created successfully", result.output
    ).group(1)
    assert os.path.exists(venv_path)


@pytest.mark.usefixtures("fake_create")
def test_venv_create_in_project(invoke, project):
    project.project_config["venv.in_project"] = True
    invoke(["venv", "create"], obj=project, strict=True)
    invoke(["venv", "create"], obj=project, strict=True)
    venv_path = project.root / ".venv"
    assert venv_path.exists()
    assert len(os.listdir(project.root / "venvs")) == 1


@pytest.mark.usefixtures("fake_create")
def test_venv_list(invoke, project):
    project.project_config["venv.in_project"] = False
    result = invoke(["venv", "create"], obj=project)
    assert result.exit_code == 0, result.stderr
    venv_path = re.match(
        r"Virtualenv (.+) is created successfully", result.output
    ).group(1)

    result = invoke(["venv", "list"], obj=project)
    assert result.exit_code == 0, result.stderr
    assert venv_path in result.output


@pytest.mark.usefixtures("fake_create")
def test_venv_remove(invoke, project):
    project.project_config["venv.in_project"] = False
    result = invoke(["venv", "create"], obj=project)
    assert result.exit_code == 0, result.stderr
    venv_path = re.match(
        r"Virtualenv (.+) is created successfully", result.output
    ).group(1)
    key = venv_path.rsplit("-", 1)[-1]

    result = invoke(["venv", "remove", "non-exist"], obj=project)
    assert result.exit_code != 0

    result = invoke(["venv", "remove", "-y", key], obj=project)
    assert result.exit_code == 0, result.stderr

    assert not os.path.exists(venv_path)


@pytest.mark.usefixtures("fake_create")
def test_venv_recreate(invoke, project):
    project.project_config["venv.in_project"] = False
    result = invoke(["venv", "create"], obj=project)
    assert result.exit_code == 0, result.stderr

    result = invoke(["venv", "create"], obj=project)
    assert result.exit_code != 0

    result = invoke(["venv", "create", "-f"], obj=project)
    assert result.exit_code == 0, result.stderr


@pytest.mark.usefixtures("venv_backends")
def test_venv_activate(invoke, mocker, project):
    project.project_config["venv.in_project"] = False
    result = invoke(["venv", "create"], obj=project)
    assert result.exit_code == 0, result.stderr
    venv_path = re.match(
        r"Virtualenv (.+) is created successfully", result.output
    ).group(1)
    key = venv_path.rsplit("-", 1)[-1]

    mocker.patch("shellingham.detect_shell", return_value=("bash", None))
    result = invoke(["venv", "activate", key], obj=project)
    assert result.exit_code == 0, result.stderr
    backend = project.config["venv.backend"]

    if backend == "conda":
        assert result.output.startswith("conda activate")
    else:
        assert result.output.strip("'\"\n").endswith("activate")
        assert result.output.startswith("source")


@pytest.mark.usefixtures("fake_create")
@pytest.mark.parametrize("keep_pypackages", [True, False])
def test_venv_auto_create(invoke, mocker, project, keep_pypackages):
    creator = mocker.patch("pdm.cli.commands.venv.backends.Backend.create")
    del project.project_config["python.path"]
    if keep_pypackages:
        project.root.joinpath("__pypackages__").mkdir(exist_ok=True)
    else:
        shutil.rmtree(project.root / "__pypackages__", ignore_errors=True)
    project.project_config["python.use_venv"] = True
    invoke(["install"], obj=project)
    if keep_pypackages:
        creator.assert_not_called()
    else:
        creator.assert_called_once()


@pytest.mark.usefixtures("fake_create")
def test_venv_purge(invoke, project):
    project.project_config["venv.in_project"] = False
    result = invoke(["venv", "purge"], obj=project)
    assert result.exit_code == 0, result.stderr

    result = invoke(["venv", "create"], obj=project)
    assert result.exit_code == 0, result.stderr
    venv_path = re.match(
        r"Virtualenv (.+) is created successfully", result.output
    ).group(1)
    result = invoke(["venv", "purge"], input="y", obj=project)
    assert result.exit_code == 0, result.stderr
    assert not os.path.exists(venv_path)


@pytest.mark.usefixtures("fake_create")
def test_venv_purge_force(invoke, project):
    project.project_config["venv.in_project"] = False
    result = invoke(["venv", "create"], obj=project)
    assert result.exit_code == 0, result.stderr
    venv_path = re.match(
        r"Virtualenv (.+) is created successfully", result.output
    ).group(1)
    result = invoke(["venv", "purge", "-f"], obj=project)
    assert result.exit_code == 0, result.stderr
    assert not os.path.exists(venv_path)


user_options = [("none", True), ("0", False), ("all", False)]


@pytest.mark.usefixtures("venv_backends")
@pytest.mark.parametrize("user_choices, is_path_exists", user_options)
def test_venv_purge_interactive(invoke, user_choices, is_path_exists, project):
    project.project_config["venv.in_project"] = False
    result = invoke(["venv", "create"], obj=project)
    assert result.exit_code == 0, result.stderr
    venv_path = re.match(
        r"Virtualenv (.+) is created successfully", result.output
    ).group(1)
    result = invoke(["venv", "purge", "-i"], input=user_choices, obj=project)
    assert result.exit_code == 0, result.stderr
    assert os.path.exists(venv_path) == is_path_exists


def test_virtualenv_backend_create(project, mocker):
    interpreter = project.python_executable
    backend = backends.VirtualenvBackend(project, None)
    assert backend.ident
    mock_call = mocker.patch("subprocess.check_call")
    location = backend.create()
    mock_call.assert_called_once_with(
        [sys.executable, "-m", "virtualenv", str(location), "-p", interpreter],
        stdout=ANY,
    )


def test_venv_backend_create(project, mocker):
    interpreter = project.python_executable
    backend = backends.VenvBackend(project, None)
    assert backend.ident
    mock_call = mocker.patch("subprocess.check_call")
    location = backend.create()
    mock_call.assert_called_once_with(
        [interpreter, "-m", "venv", str(location)], stdout=ANY
    )


def test_conda_backend_create(project, mocker):
    backend = backends.CondaBackend(project, "3.8")
    assert backend.ident == "3.8"
    mock_call = mocker.patch("subprocess.check_call")
    location = backend.create()
    mock_call.assert_called_once_with(
        ["conda", "create", "--yes", "--prefix", str(location), "pip", "python=3.8"],
        stdout=ANY,
    )

    backend = backends.CondaBackend(project, None)
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    assert backend.ident == python_version
    location = backend.create()
    mock_call.assert_called_with(
        [
            "conda",
            "create",
            "--yes",
            "--prefix",
            str(location),
            "pip",
            f"python={python_version}",
        ],
        stdout=ANY,
    )
