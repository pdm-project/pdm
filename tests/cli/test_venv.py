import os
import re
import shutil
import sys
from unittest.mock import ANY

import pytest

from pdm.cli.commands.venv import backends
from pdm.cli.commands.venv.utils import get_venv_prefix


@pytest.fixture(params=[True, False])
def with_pip(request):
    return request.param


@pytest.fixture()
def fake_create(monkeypatch):
    def fake_create(self, location, *args, prompt=None):
        location.mkdir(parents=True)

    monkeypatch.setattr(backends.VirtualenvBackend, "perform_create", fake_create)
    monkeypatch.setattr(backends.VenvBackend, "perform_create", fake_create)
    monkeypatch.setattr(backends.CondaBackend, "perform_create", fake_create)


@pytest.mark.usefixtures("fake_create")
def test_venv_create(invoke, project):
    project.project_config.pop("python.path", None)
    project.project_config["venv.in_project"] = False
    result = invoke(["venv", "create"], obj=project)
    assert result.exit_code == 0, result.stderr
    venv_path = re.match(r"Virtualenv (.+) is created successfully", result.output).group(1)
    assert os.path.exists(venv_path)
    assert "python.path" not in project.project_config


@pytest.mark.usefixtures("fake_create")
def test_venv_create_in_project(invoke, project):
    project.project_config["venv.in_project"] = True
    invoke(["venv", "create"], obj=project, strict=True)
    venv_path = project.root / ".venv"
    assert venv_path.exists()
    result = invoke(["venv", "create"], obj=project)
    assert result.exit_code == 1
    assert "is not empty" in result.stderr


@pytest.mark.usefixtures("fake_create")
def test_venv_list(invoke, project):
    project.project_config["venv.in_project"] = False
    result = invoke(["venv", "create"], obj=project)
    assert result.exit_code == 0, result.stderr
    venv_path = re.match(r"Virtualenv (.+) is created successfully", result.output).group(1)

    result = invoke(["venv", "list"], obj=project)
    assert result.exit_code == 0, result.stderr
    assert venv_path in result.output


@pytest.mark.usefixtures("fake_create")
def test_venv_remove(invoke, project):
    project.project_config["venv.in_project"] = False
    result = invoke(["venv", "create"], obj=project)
    assert result.exit_code == 0, result.stderr
    venv_path = re.match(r"Virtualenv (.+) is created successfully", result.output).group(1)
    key = os.path.basename(venv_path)[len(get_venv_prefix(project)) :]

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
    venv_path = re.match(r"Virtualenv (.+) is created successfully", result.output).group(1)
    key = os.path.basename(venv_path)[len(get_venv_prefix(project)) :]

    mocker.patch("shellingham.detect_shell", return_value=("bash", None))
    result = invoke(["venv", "activate", key], obj=project)
    assert result.exit_code == 0, result.stderr
    backend = project.config["venv.backend"]

    if backend == "conda":
        assert result.output.startswith("conda activate")
    else:
        assert result.output.strip("'\"\n").endswith("activate")
        assert result.output.startswith("source")


@pytest.mark.usefixtures("venv_backends")
def test_venv_activate_custom_prompt(invoke, mocker, project):
    project.project_config["venv.in_project"] = False
    creator = mocker.patch("pdm.cli.commands.venv.backends.Backend.create")
    result = invoke(["venv", "create"], obj=project)
    assert result.exit_code == 0, result.stderr
    creator.assert_called_once_with(
        None, [], False, False, prompt=project.project_config["venv.prompt"], with_pip=False
    )


def test_venv_activate_project_without_python(invoke, project):
    project.project_config.pop("python.path", None)
    result = invoke(["venv", "activate"], obj=project)
    assert result.exit_code != 0
    assert "The project doesn't have a saved python.path" in result.stderr


@pytest.mark.usefixtures("fake_create")
def test_venv_activate_error(invoke, project):
    project.project_config["venv.in_project"] = False
    result = invoke(["venv", "create"], obj=project, strict=True)

    result = invoke(["venv", "activate", "foo"], obj=project)
    assert result.exit_code != 0
    assert "No virtualenv with key" in result.stderr

    project.project_config["python.path"] = os.path.abspath("fake/bin/python")
    result = invoke(["venv", "activate"], obj=project)
    print(project.project_config.get("python.path"))
    assert result.exit_code != 0, result.output + result.stderr
    assert "Can't activate a non-venv Python" in result.stderr


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
    venv_path = re.match(r"Virtualenv (.+) is created successfully", result.output).group(1)
    result = invoke(["venv", "purge"], input="y", obj=project)
    assert result.exit_code == 0, result.stderr
    assert not os.path.exists(venv_path)


@pytest.mark.usefixtures("fake_create")
def test_venv_purge_force(invoke, project):
    project.project_config["venv.in_project"] = False
    result = invoke(["venv", "create"], obj=project)
    assert result.exit_code == 0, result.stderr
    venv_path = re.match(r"Virtualenv (.+) is created successfully", result.output).group(1)
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
    venv_path = re.match(r"Virtualenv (.+) is created successfully", result.output).group(1)
    result = invoke(["venv", "purge", "-i"], input=user_choices, obj=project)
    assert result.exit_code == 0, result.stderr
    assert os.path.exists(venv_path) == is_path_exists


def test_virtualenv_backend_create(project, mocker, with_pip):
    backend = backends.VirtualenvBackend(project, None)
    assert backend.ident
    mock_call = mocker.patch("subprocess.check_call")
    location = backend.create(with_pip=with_pip)
    pip_args = [] if with_pip else ["--no-pip", "--no-setuptools", "--no-wheel"]
    mock_call.assert_called_once_with(
        [
            sys.executable,
            "-m",
            "virtualenv",
            str(location),
            "-p",
            str(backend._resolved_interpreter.executable),
            *pip_args,
        ],
        stdout=ANY,
    )


def test_venv_backend_create(project, mocker, with_pip):
    backend = backends.VenvBackend(project, None)
    assert backend.ident
    mock_call = mocker.patch("subprocess.check_call")
    location = backend.create(with_pip=with_pip)
    pip_args = [] if with_pip else ["--without-pip"]
    mock_call.assert_called_once_with(
        [
            str(backend._resolved_interpreter.executable),
            "-m",
            "venv",
            str(location),
            *pip_args,
        ],
        stdout=ANY,
    )


def test_conda_backend_create(project, mocker, with_pip):
    backend = backends.CondaBackend(project, "3.8")
    assert backend.ident == "3.8"
    mock_call = mocker.patch("subprocess.check_call")
    location = backend.create(with_pip=with_pip)
    pip_args = ["pip"] if with_pip else []
    mock_call.assert_called_once_with(
        [
            "conda",
            "create",
            "--yes",
            "--prefix",
            str(location),
            "python=3.8",
            *pip_args,
        ],
        stdout=ANY,
    )

    backend = backends.CondaBackend(project, None)
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    assert backend.ident.startswith(python_version)
    location = backend.create()
    mock_call.assert_called_with(
        [
            "conda",
            "create",
            "--yes",
            "--prefix",
            str(location),
            f"python={python_version}",
        ],
        stdout=ANY,
    )
