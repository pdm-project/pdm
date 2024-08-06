import os
import platform
import re
import shutil
import sys
from unittest.mock import ANY

import pytest
import shellingham

from pdm.cli.commands.venv import backends
from pdm.cli.commands.venv.utils import get_venv_prefix


@pytest.fixture(params=[True, False])
def with_pip(request):
    return request.param


@pytest.fixture()
def fake_create(monkeypatch):
    def fake_create(self, location, *args, prompt=None):
        bin_dir = "Scripts" if sys.platform == "win32" else "bin"
        suffix = ".exe" if sys.platform == "win32" else ""
        (location / bin_dir).mkdir(parents=True)
        (location / bin_dir / f"python{suffix}").touch()

    monkeypatch.setattr(backends.VirtualenvBackend, "perform_create", fake_create)
    monkeypatch.setattr(backends.VenvBackend, "perform_create", fake_create)
    monkeypatch.setattr(backends.CondaBackend, "perform_create", fake_create)


@pytest.mark.usefixtures("fake_create")
def test_venv_create(pdm, project):
    project._saved_python = None
    project.project_config["venv.in_project"] = False
    result = pdm(["venv", "create"], obj=project)
    assert result.exit_code == 0, result.stderr
    venv_path = re.match(r"Virtualenv (.+) is created successfully", result.output).group(1)
    assert os.path.exists(venv_path)
    assert not project._saved_python


@pytest.mark.usefixtures("fake_create")
def test_venv_create_in_project(pdm, project):
    project.project_config["venv.in_project"] = True
    pdm(["venv", "create"], obj=project, strict=True)
    venv_path = project.root / ".venv"
    assert venv_path.exists()
    result = pdm(["venv", "create"], obj=project)
    assert result.exit_code == 1
    assert "is not empty" in result.stderr


@pytest.mark.usefixtures("fake_create")
def test_venv_create_other_location(pdm, project):
    pdm(["venv", "-p", project.root.as_posix(), "create"], strict=True)
    venv_path = project.root / ".venv"
    assert venv_path.exists()
    result = pdm(["venv", "-p", project.root.as_posix(), "create"])
    assert result.exit_code == 1
    assert "is not empty" in result.stderr


@pytest.mark.usefixtures("fake_create")
def test_venv_show_path(pdm, project):
    project.project_config["venv.in_project"] = True
    pdm(["venv", "create"], obj=project, strict=True)
    pdm(["venv", "create", "--name", "test"], obj=project, strict=True)
    result = pdm(["venv", "--path", "in-project"], obj=project, strict=True)
    assert result.output.strip() == str(project.root / ".venv")
    result = pdm(["venv", "--path", "test"], obj=project)
    assert result.exit_code == 0
    result = pdm(["venv", "--path", "foo"], obj=project)
    assert result.exit_code == 1


@pytest.mark.usefixtures("fake_create")
def test_venv_list(pdm, project):
    project.project_config["venv.in_project"] = False
    result = pdm(["venv", "create"], obj=project)
    assert result.exit_code == 0, result.stderr
    venv_path = re.match(r"Virtualenv (.+) is created successfully", result.output).group(1)

    result = pdm(["venv", "list"], obj=project)
    assert result.exit_code == 0, result.stderr
    assert venv_path in result.output


@pytest.mark.usefixtures("fake_create")
def test_venv_remove(pdm, project):
    project.project_config["venv.in_project"] = False
    result = pdm(["venv", "create"], obj=project)
    assert result.exit_code == 0, result.stderr
    venv_path = re.match(r"Virtualenv (.+) is created successfully", result.output).group(1)
    key = os.path.basename(venv_path)[len(get_venv_prefix(project)) :]

    result = pdm(["venv", "remove", "non-exist"], obj=project)
    assert result.exit_code != 0

    result = pdm(["venv", "remove", "-y", key], obj=project)
    assert result.exit_code == 0, result.stderr

    assert not os.path.exists(venv_path)


@pytest.mark.usefixtures("fake_create")
def test_venv_recreate(pdm, project):
    project.project_config["venv.in_project"] = False
    result = pdm(["venv", "create"], obj=project)
    assert result.exit_code == 0, result.stderr

    result = pdm(["venv", "create"], obj=project)
    assert result.exit_code != 0

    result = pdm(["venv", "create", "-f"], obj=project)
    assert result.exit_code == 0, result.stderr


@pytest.mark.usefixtures("venv_backends")
def test_venv_activate(pdm, mocker, project):
    project.project_config["venv.in_project"] = False
    result = pdm(["venv", "create"], obj=project)
    assert result.exit_code == 0, result.stderr
    venv_path = re.match(r"Virtualenv (.+) is created successfully", result.output).group(1)
    key = os.path.basename(venv_path)[len(get_venv_prefix(project)) :]

    mocker.patch("shellingham.detect_shell", return_value=("bash", None))
    result = pdm(["venv", "activate", key], obj=project)
    assert result.exit_code == 0, result.stderr
    backend = project.config["venv.backend"]

    if backend == "conda":
        assert result.output.startswith("conda activate")
    else:
        assert result.output.strip("'\"\n").endswith("activate")
        if platform.system() == "Windows":
            assert not result.output.startswith("source")
            assert not result.output.startswith("'")
        else:
            assert result.output.startswith("source")


@pytest.mark.usefixtures("venv_backends")
def test_venv_activate_custom_prompt(pdm, mocker, project):
    project.project_config["venv.in_project"] = False
    creator = mocker.patch("pdm.cli.commands.venv.backends.Backend.create")
    result = pdm(["venv", "create"], obj=project)
    assert result.exit_code == 0, result.stderr
    creator.assert_called_once_with(
        None, [], False, False, prompt=project.project_config["venv.prompt"], with_pip=False
    )


def test_venv_activate_project_without_python(pdm, project):
    project._saved_python = None
    result = pdm(["venv", "activate"], obj=project)
    assert result.exit_code != 0
    assert "The project doesn't have a saved python.path" in result.stderr


@pytest.mark.usefixtures("fake_create")
def test_venv_activate_error(pdm, project):
    project.project_config["venv.in_project"] = False
    result = pdm(["venv", "create"], obj=project, strict=True)

    result = pdm(["venv", "activate", "foo"], obj=project)
    assert result.exit_code != 0
    assert "No virtualenv with key" in result.stderr

    project._saved_python = os.path.abspath("fake/bin/python")
    result = pdm(["venv", "activate"], obj=project)
    assert result.exit_code != 0, result.output + result.stderr
    assert "Can't activate a non-venv Python" in result.stderr


@pytest.mark.usefixtures("venv_backends")
def test_venv_activate_no_shell(pdm, mocker, project):
    project.project_config["venv.in_project"] = False
    result = pdm(["venv", "create"], obj=project)
    assert result.exit_code == 0, result.stderr
    venv_path = re.match(r"Virtualenv (.+) is created successfully", result.output).group(1)
    key = os.path.basename(venv_path)[len(get_venv_prefix(project)) :]

    mocker.patch("shellingham.detect_shell", side_effect=shellingham.ShellDetectionFailure())
    result = pdm(["venv", "activate", key], obj=project)
    assert result.exit_code == 0, result.stderr
    backend = project.config["venv.backend"]

    if backend == "conda":
        assert result.output.startswith("conda activate")
    else:
        assert result.output.strip("'\"\n").endswith("activate")
        if platform.system() == "Windows":
            assert not result.output.startswith("source")
            assert not result.output.startswith("'")
        else:
            assert result.output.startswith("source")


@pytest.mark.usefixtures("fake_create")
@pytest.mark.parametrize("keep_pypackages", [True, False])
def test_venv_auto_create(pdm, mocker, project, keep_pypackages):
    creator = mocker.patch("pdm.cli.commands.venv.backends.Backend.create")
    project._saved_python = None
    if keep_pypackages:
        project.root.joinpath("__pypackages__").mkdir(exist_ok=True)
    else:
        shutil.rmtree(project.root / "__pypackages__", ignore_errors=True)
    project.project_config["python.use_venv"] = True
    pdm(["install", "--no-self"], obj=project)
    if keep_pypackages:
        creator.assert_not_called()
    else:
        creator.assert_called_once()


@pytest.mark.usefixtures("fake_create")
def test_venv_purge(pdm, project):
    project.project_config["venv.in_project"] = False
    result = pdm(["venv", "purge"], obj=project)
    assert result.exit_code == 0, result.stderr

    result = pdm(["venv", "create"], obj=project)
    assert result.exit_code == 0, result.stderr
    venv_path = re.match(r"Virtualenv (.+) is created successfully", result.output).group(1)
    result = pdm(["venv", "purge"], input="y", obj=project)
    assert result.exit_code == 0, result.stderr
    assert not os.path.exists(venv_path)


@pytest.mark.usefixtures("fake_create")
def test_venv_purge_force(pdm, project):
    project.project_config["venv.in_project"] = False
    result = pdm(["venv", "create"], obj=project)
    assert result.exit_code == 0, result.stderr
    venv_path = re.match(r"Virtualenv (.+) is created successfully", result.output).group(1)
    result = pdm(["venv", "purge", "-f"], obj=project)
    assert result.exit_code == 0, result.stderr
    assert not os.path.exists(venv_path)


user_options = [("none", True), ("0", False), ("all", False)]


@pytest.mark.usefixtures("venv_backends")
@pytest.mark.parametrize("user_choices, is_path_exists", user_options)
def test_venv_purge_interactive(pdm, user_choices, is_path_exists, project):
    project.project_config["venv.in_project"] = False
    result = pdm(["venv", "create"], obj=project)
    assert result.exit_code == 0, result.stderr
    venv_path = re.match(r"Virtualenv (.+) is created successfully", result.output).group(1)
    result = pdm(["venv", "purge", "-i"], input=user_choices, obj=project)
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
    assert project.python
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
