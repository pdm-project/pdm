import os
from pathlib import Path

import distlib.wheel
import pytest

from pdm.models.requirements import filter_requirements_with_extras
from pdm.pep517.api import build_wheel
from pdm.project import Project
from pdm.utils import cd


def test_project_python_with_pyenv_support(project, mocker):
    from pythonfinder.environment import PYENV_ROOT

    del project.project_config["python.path"]
    pyenv_python = os.path.join(PYENV_ROOT, "shims", "python")

    mocker.patch("pdm.models.environment.PYENV_INSTALLED", True)
    assert project.environment.python_executable == pyenv_python

    # Clean cache
    del project.environment.__dict__["python_executable"]

    project.project_config["python.use_pyenv"] = False
    assert project.environment.python_executable != pyenv_python


def test_project_config_items(project):
    config = project.config

    for item in ("python.use_pyenv", "pypi.url", "cache_dir"):
        assert item in config


def test_project_config_set_invalid_key(project):
    config = project.project_config

    with pytest.raises(KeyError):
        config["foo"] = "bar"


def test_project_sources_overriding(project):
    project.project_config["pypi.url"] = "https://testpypi.org/simple"
    assert project.sources[0]["url"] == "https://testpypi.org/simple"

    project.tool_settings["source"] = [
        {"url": "https://example.org/simple", "name": "pypi", "verify_ssl": True}
    ]
    assert project.sources[0]["url"] == "https://example.org/simple"


def test_global_project(tmp_path):
    project = Project.create_global(tmp_path.as_posix())
    project.init_global_project()
    assert project.environment.is_global


def test_project_use_venv(project, mocker):
    del project.project_config["python.path"]
    scripts = "Scripts" if os.name == "nt" else "bin"
    suffix = ".exe" if os.name == "nt" else ""

    os.environ["VIRTUAL_ENV"] = "/path/to/env"
    mocker.patch("pdm.models.environment.get_python_version", return_value="3.7.0")

    project.project_config["use_venv"] = True
    env = project.environment
    assert (
        Path(env.python_executable)
        == Path("/path/to/env") / scripts / f"python{suffix}"
    )
    assert env.is_global


def test_project_with_combined_extras(fixture_project):
    project = fixture_project("demo-combined-extras")
    (project.root / "build").mkdir(exist_ok=True)
    with cd(project.root.as_posix()):
        wheel_name = build_wheel(str(project.root / "build"))
        wheel = distlib.wheel.Wheel(str(project.root / "build" / wheel_name))

    all_requires = filter_requirements_with_extras(
        wheel.metadata.run_requires, ("all",)
    )
    for dep in ("urllib3", "chardet", "idna"):
        assert dep in all_requires
