import os

import pytest


def test_project_python_with_pyenv_support(project, mocker):
    from pythonfinder.environment import PYENV_ROOT

    pyenv_python = os.path.join(PYENV_ROOT, "shims", "python")

    mocker.patch("pdm.models.environment.PYENV_INSTALLED", True)
    assert project.environment.python_executable == pyenv_python

    project.config["python.use_pyenv"] = False
    assert project.environment.python_executable != pyenv_python


def test_project_config_items(project):
    config = project.config

    for item in ("python.use_pyenv", "pypi.url", "cache_dir"):
        assert item in config


def test_project_config_set_invalid_key(project):
    config = project.config

    with pytest.raises(KeyError):
        config["foo"] = "bar"


def test_project_config_save_global_local(project):
    config = project.config
    config["cache_dir"] = "foo_path"
    config.save_config(True)
    assert config._global_config["cache_dir"] == "foo_path"

    config["cache_dir"] = "some_path"
    config.save_config(False)
    assert config._global_config["cache_dir"] == "foo_path"
    assert config._project_config["cache_dir"] == "some_path"


def test_project_sources_overriding(project):
    project.config["pypi.url"] = "https://testpypi.org/simple"
    assert project.sources[0]["url"] == "https://testpypi.org/simple"

    project.tool_settings["source"] = [
        {"url": "https://example.org/simple", "name": "pypi", "verify_ssl": True}
    ]
    assert project.sources[0]["url"] == "https://example.org/simple"
