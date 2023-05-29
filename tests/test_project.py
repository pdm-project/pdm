import os
import sys
import venv
from pathlib import Path

import pytest
from packaging.version import parse
from pytest_httpserver import HTTPServer

from pdm.environments import PythonEnvironment
from pdm.exceptions import PdmException
from pdm.models.venv import get_venv_python
from pdm.utils import cd


def test_project_python_with_pyenv_support(project, mocker, monkeypatch):
    project._saved_python = None
    project._python = None
    monkeypatch.setenv("PDM_IGNORE_SAVED_PYTHON", "1")
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
    mocker.patch("findpython.python.PythonVersion._get_interpreter", return_value=sys.executable)
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


def test_project_sources_overriding_pypi(project):
    project.project_config["pypi.url"] = "https://test.pypi.org/simple"
    assert project.sources[0].url == "https://test.pypi.org/simple"

    project.pyproject.settings["source"] = [{"url": "https://example.org/simple", "name": "pypi", "verify_ssl": True}]
    assert project.sources[0].url == "https://example.org/simple"


def test_project_sources_env_var_expansion(project, monkeypatch):
    monkeypatch.setenv("PYPI_USER", "user")
    monkeypatch.setenv("PYPI_PASS", "password")
    project.project_config["pypi.url"] = "https://${PYPI_USER}:${PYPI_PASS}@test.pypi.org/simple"
    # expanded in sources
    assert project.sources[0].url == "https://user:password@test.pypi.org/simple"
    # not expanded in project config
    assert project.project_config["pypi.url"] == "https://${PYPI_USER}:${PYPI_PASS}@test.pypi.org/simple"

    project.pyproject.settings["source"] = [
        {
            "url": "https://${PYPI_USER}:${PYPI_PASS}@example.org/simple",
            "name": "pypi",
            "verify_ssl": True,
        }
    ]
    # expanded in sources
    assert project.sources[0].url == "https://user:password@example.org/simple"
    # not expanded in tool settings
    assert project.pyproject.settings["source"][0]["url"] == "https://${PYPI_USER}:${PYPI_PASS}@example.org/simple"

    project.pyproject.settings["source"] = [
        {
            "url": "https://${PYPI_USER}:${PYPI_PASS}@example2.org/simple",
            "name": "example2",
            "verify_ssl": True,
        }
    ]
    # expanded in sources
    assert project.sources[1].url == "https://user:password@example2.org/simple"
    # not expanded in tool settings
    assert project.pyproject.settings["source"][0]["url"] == "https://${PYPI_USER}:${PYPI_PASS}@example2.org/simple"


def test_global_project(tmp_path, core):
    project = core.create_project(tmp_path, True)
    assert project.is_global
    assert isinstance(project.environment, PythonEnvironment)


def test_auto_global_project(tmp_path, core):
    tmp_path.joinpath(".pdm-home").mkdir()
    (tmp_path / ".pdm-home/config.toml").write_text("[global_project]\nfallback = true\n")
    with cd(tmp_path):
        project = core.create_project(global_config=tmp_path / ".pdm-home/config.toml")
    assert project.is_global


def test_project_use_venv(project):
    project._saved_python = None
    project._python = None
    scripts = "Scripts" if os.name == "nt" else "bin"
    suffix = ".exe" if os.name == "nt" else ""
    venv.create(project.root / "venv")

    project.project_config["python.use_venv"] = True
    env = project.environment
    assert env.interpreter.executable == project.root / "venv" / scripts / f"python{suffix}"
    assert not env.is_local


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
    project._saved_python = (project.root / "test_venv" / scripts / f"python{suffix}").as_posix()

    assert not project.environment.is_local


@pytest.mark.path
def test_ignore_saved_python(project, monkeypatch):
    project.project_config["python.use_venv"] = True
    project._python = None
    scripts = "Scripts" if os.name == "nt" else "bin"
    suffix = ".exe" if os.name == "nt" else ""
    venv.create(project.root / "venv")
    monkeypatch.setenv("PDM_IGNORE_SAVED_PYTHON", "1")
    assert project.python.executable != project._saved_python
    assert project.python.executable == project.root / "venv" / scripts / f"python{suffix}"


def test_select_dependencies(project):
    project.pyproject.metadata["dependencies"] = ["requests"]
    project.pyproject.metadata["optional-dependencies"] = {
        "security": ["cryptography"],
        "venv": ["virtualenv"],
    }
    project.pyproject.settings["dev-dependencies"] = {
        "test": ["pytest"],
        "doc": ["mkdocs"],
    }
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


@pytest.mark.path
def test_set_non_exist_python_path(project_no_init):
    project_no_init._saved_python = "non-exist-python"
    project_no_init._python = None
    assert project_no_init.python.executable.name != "non-exist-python"


@pytest.mark.usefixtures("venv_backends")
def test_create_venv_first_time(pdm, project, local_finder):
    project.project_config.update({"venv.in_project": False})
    project._saved_python = None
    result = pdm(["install"], obj=project)
    assert result.exit_code == 0
    venv_parent = project.root / "venvs"
    venv_path = next(venv_parent.iterdir(), None)
    assert venv_path is not None

    assert Path(project._saved_python).relative_to(venv_path)


@pytest.mark.usefixtures("venv_backends", "local_finder")
@pytest.mark.parametrize("with_pip", [True, False])
def test_create_venv_in_project(pdm, project, with_pip):
    project.project_config.update({"venv.in_project": True, "venv.with_pip": with_pip})
    project._saved_python = None
    result = pdm(["install"], obj=project)
    assert result.exit_code == 0
    assert project.root.joinpath(".venv").exists()
    working_set = project.environment.get_working_set()
    assert ("pip" in working_set) is with_pip


@pytest.mark.usefixtures("venv_backends")
def test_find_interpreters_from_venv(pdm, project, local_finder):
    project.project_config.update({"venv.in_project": False})
    project._saved_python = None
    result = pdm(["install"], obj=project)
    assert result.exit_code == 0
    venv_parent = project.root / "venvs"
    venv_path = next(venv_parent.iterdir(), None)
    venv_python = get_venv_python(venv_path)

    assert any(venv_python == p.executable for p in project.find_interpreters())


@pytest.mark.usefixtures("local_finder")
def test_find_interpreters_without_duplicate_relative_paths(pdm, project):
    project._saved_python = None
    venv.create(project.root / ".venv", clear=True)
    with cd(project.root):
        bin_dir = "Scripts" if os.name == "nt" else "bin"
        suffix = ".exe" if os.name == "nt" else ""
        found = list(project.find_interpreters(f".venv/{bin_dir}/python{suffix}"))
        assert len(found) == 1


def test_iter_project_venvs(project):
    from pdm.cli.commands.venv.utils import get_venv_prefix, iter_venvs
    from pdm.models.venv import get_venv_python

    venv_parent = Path(project.config["venv.location"])
    venv_prefix = get_venv_prefix(project)
    for name in ("foo", "bar", "baz"):
        venv_python = get_venv_python(venv_parent / (venv_prefix + name))
        venv_python.parent.mkdir(parents=True)
        venv_python.touch()
    dot_venv_python = get_venv_python(project.root / ".venv")
    dot_venv_python.parent.mkdir(parents=True)
    dot_venv_python.touch()
    venv_keys = [key for key, _ in iter_venvs(project)]
    assert sorted(venv_keys) == ["bar", "baz", "foo", "in-project"]


def test_load_extra_sources(project):
    project.pyproject.settings["source"] = [
        {
            "name": "custom",
            "url": "https://custom.pypi.org/simple",
        }
    ]
    project.global_config["pypi.extra.url"] = "https://extra.pypi.org/simple"
    sources = project.sources
    assert len(sources) == 3
    assert [item.name for item in sources] == ["pypi", "custom", "extra"]

    project.global_config["pypi.ignore_stored_index"] = True
    sources = project.sources
    assert len(sources) == 1
    assert [item.name for item in sources] == ["custom"]


def test_no_index_raise_error(project):
    project.global_config["pypi.ignore_stored_index"] = True
    with pytest.raises(PdmException, match="You must specify at least one index"):
        with project.environment.get_finder():
            pass


def test_access_index_with_auth(project, httpserver: HTTPServer):
    httpserver.expect_request(
        "/simple/my-package", method="GET", headers={"Authorization": "Basic Zm9vOmJhcg=="}
    ).respond_with_data("OK")
    project.global_config.update(
        {
            "pypi.extra.url": httpserver.url_for("/simple"),
            "pypi.extra.username": "foo",
            "pypi.extra.password": "bar",
        }
    )
    with project.environment.get_finder() as finder:
        session = finder.session
        resp = session.get(httpserver.url_for("/simple/my-package"))
        assert resp.ok


def test_configured_source_overwriting(project):
    project.pyproject.settings["source"] = [
        {
            "name": "custom",
            "url": "https://custom.pypi.org/simple",
        }
    ]
    project.global_config["pypi.custom.url"] = "https://extra.pypi.org/simple"
    project.global_config["pypi.custom.verify_ssl"] = False
    project.project_config["pypi.custom.username"] = "foo"
    project.project_config["pypi.custom.password"] = "bar"
    sources = project.sources
    assert [source.name for source in sources] == ["pypi", "custom"]
    custom_source = sources[1]
    assert custom_source.url == "https://custom.pypi.org/simple"
    assert custom_source.verify_ssl is False
    assert custom_source.username == "foo"
    assert custom_source.password == "bar"


def test_invoke_pdm_adding_configured_args(project, pdm, mocker):
    project.pyproject.settings["options"] = {
        "install": ["--no-self", "--no-editable"],
        "add": ["--no-isolation"],
        "lock": ["--no-cross-platform"],
    }
    project.pyproject.write()
    parser = mocker.patch("argparse.ArgumentParser.parse_args")
    pdm(["add", "requests"], obj=project)
    parser.assert_called_with(["add", "--no-isolation", "requests"])
    pdm(["install", "--check"], obj=project)
    parser.assert_called_with(["install", "--no-self", "--no-editable", "--check"])
    pdm(["lock", "--lockfile", "pdm.2.lock"], obj=project)
    parser.assert_called_with(["lock", "--no-cross-platform", "--lockfile", "pdm.2.lock"])
