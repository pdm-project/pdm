import os
import sys
import venv
from pathlib import Path

import pytest
from packaging.version import parse

from pdm.utils import cd


def test_project_python_with_pyenv_support(project, mocker):

    del project.project_config["python.path"]
    project._python = None
    os.environ["PDM_IGNORE_SAVED_PYTHON"] = "1"
    mocker.patch("pdm.project.core.PYENV_ROOT", str(project.root))
    pyenv_python = project.root / "shims/python"
    if os.name == "nt":
        pyenv_python = pyenv_python.with_suffix(".bat")
    pyenv_python.parent.mkdir()
    pyenv_python.touch()
    mocker.patch(
        "findpython.python.PythonVersion._get_version",
        return_value=parse("3.8.0"),
    )
    mocker.patch(
        "findpython.python.PythonVersion._get_interpreter", return_value=sys.executable
    )
    assert Path(project.python.path) == pyenv_python
    assert project.python.executable == Path(sys.executable)

    # Clean cache
    project._python = None

    project.project_config["python.use_pyenv"] = False
    assert Path(project.python.path) != pyenv_python


def test_project_config_items(project):
    config = project.config

    for item in ("python.use_pyenv", "pypi.url", "cache_dir"):
        assert item in config


def test_project_config_set_invalid_key(project):
    config = project.project_config

    with pytest.raises(KeyError):
        config["foo"] = "bar"


def test_project_sources_overriding(project):
    project.project_config["pypi.url"] = "https://test.pypi.org/simple"
    assert project.sources[0]["url"] == "https://test.pypi.org/simple"

    project.tool_settings["source"] = [
        {"url": "https://example.org/simple", "name": "pypi", "verify_ssl": True}
    ]
    assert project.sources[0]["url"] == "https://example.org/simple"


def test_project_sources_env_var_expansion(project):
    os.environ["PYPI_USER"] = "user"
    os.environ["PYPI_PASS"] = "password"
    project.project_config[
        "pypi.url"
    ] = "https://${PYPI_USER}:${PYPI_PASS}@test.pypi.org/simple"
    # expanded in sources
    assert project.sources[0]["url"] == "https://user:password@test.pypi.org/simple"
    # not expanded in project config
    assert (
        project.project_config["pypi.url"]
        == "https://${PYPI_USER}:${PYPI_PASS}@test.pypi.org/simple"
    )

    project.tool_settings["source"] = [
        {
            "url": "https://${PYPI_USER}:${PYPI_PASS}@example.org/simple",
            "name": "pypi",
            "verify_ssl": True,
        }
    ]
    # expanded in sources
    assert project.sources[0]["url"] == "https://user:password@example.org/simple"
    # not expanded in tool settings
    assert (
        project.tool_settings["source"][0]["url"]
        == "https://${PYPI_USER}:${PYPI_PASS}@example.org/simple"
    )

    project.tool_settings["source"] = [
        {
            "url": "https://${PYPI_USER}:${PYPI_PASS}@example2.org/simple",
            "name": "example2",
            "verify_ssl": True,
        }
    ]
    # expanded in sources
    assert project.sources[1]["url"] == "https://user:password@example2.org/simple"
    # not expanded in tool settings
    assert (
        project.tool_settings["source"][0]["url"]
        == "https://${PYPI_USER}:${PYPI_PASS}@example2.org/simple"
    )


def test_global_project(tmp_path, core):
    project = core.create_project(tmp_path, True)
    assert project.environment.is_global


def test_auto_global_project(tmp_path, core):
    tmp_path.joinpath(".pdm-home").mkdir()
    (tmp_path / ".pdm-home/config.toml").write_text(
        "[global_project]\nfallback = true\n"
    )
    with cd(tmp_path):
        project = core.create_project(global_config=tmp_path / ".pdm-home/config.toml")
    assert project.is_global


def test_project_use_venv(project):
    del project.project_config["python.path"]
    project._python = None
    scripts = "Scripts" if os.name == "nt" else "bin"
    suffix = ".exe" if os.name == "nt" else ""
    venv.create(project.root / "venv")

    project.project_config["python.use_venv"] = True
    env = project.environment
    assert (
        env.interpreter.executable
        == project.root / "venv" / scripts / f"python{suffix}"
    )
    assert env.is_global


def test_project_packages_path(project):
    packages_path = project.environment.packages_path
    version = ".".join(map(str, sys.version_info[:2]))
    if os.name == "nt" and sys.maxsize <= 2**32:
        assert packages_path.name == version + "-32"
    else:
        assert packages_path.name == version


def test_project_auto_detect_venv(project):

    venv.create(project.root / "test_venv")

    scripts = "Scripts" if os.name == "nt" else "bin"
    suffix = ".exe" if os.name == "nt" else ""

    project.project_config["python.use_venv"] = True
    project._python = None
    project.project_config["python.path"] = (
        project.root / "test_venv" / scripts / f"python{suffix}"
    ).as_posix()

    assert project.environment.is_global


def test_ignore_saved_python(project):
    project.project_config["python.use_venv"] = True
    project._python = None
    scripts = "Scripts" if os.name == "nt" else "bin"
    suffix = ".exe" if os.name == "nt" else ""
    venv.create(project.root / "venv")
    os.environ["PDM_IGNORE_SAVED_PYTHON"] = "1"
    assert project.python.executable != project.project_config["python.path"]
    assert (
        project.python.executable == project.root / "venv" / scripts / f"python{suffix}"
    )


def test_select_dependencies(project):
    project.meta["dependencies"] = ["requests"]
    project.meta["optional-dependencies"] = {
        "security": ["cryptography"],
        "venv": ["virtualenv"],
    }
    project.tool_settings["dev-dependencies"] = {"test": ["pytest"], "doc": ["mkdocs"]}
    assert sorted(project.get_dependencies()) == ["requests"]
    assert sorted(project.dependencies) == ["requests"]

    assert sorted(project.get_dependencies("security")) == ["cryptography"]
    assert sorted(project.get_dependencies("test")) == ["pytest"]
    assert sorted(project.dev_dependencies) == ["mkdocs", "pytest"]

    assert sorted(project.iter_groups()) == [
        "default",
        "doc",
        "security",
        "test",
        "venv",
    ]


def test_global_python_path_config(project_no_init, tmp_path):
    tmp_path.joinpath(".pdm.toml").unlink()
    project_no_init.global_config["python.path"] = sys.executable
    # Recreate the project to clean cached properties
    p = project_no_init.core.create_project(
        project_no_init.root, global_config=tmp_path / ".pdm-home/config.toml"
    )
    assert p.python.executable == Path(sys.executable)
    assert "python.path" not in p.project_config


@pytest.mark.path
def test_set_non_exist_python_path(project_no_init):
    project_no_init.project_config["python.path"] = "non-exist-python"
    project_no_init._python = None
    assert project_no_init.python.executable == Path(sys.executable)
