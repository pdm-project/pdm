import pytest

from pdm.exceptions import PdmUsageError
from pdm.utils import cd


def test_config_command(project, invoke):
    result = invoke(["config"], obj=project)
    assert result.exit_code == 0
    assert "python.use_pyenv = True" in result.output

    result = invoke(["config", "-v"], obj=project)
    assert result.exit_code == 0
    assert "Use the pyenv interpreter" in result.output


def test_config_get_command(project, invoke):
    result = invoke(["config", "python.use_pyenv"], obj=project)
    assert result.exit_code == 0
    assert result.output.strip() == "True"

    result = invoke(["config", "foo.bar"], obj=project)
    assert result.exit_code != 0


def test_config_set_command(project, invoke):
    result = invoke(["config", "python.use_pyenv", "false"], obj=project)
    assert result.exit_code == 0
    result = invoke(["config", "python.use_pyenv"], obj=project)
    assert result.output.strip() == "False"

    result = invoke(["config", "foo.bar"], obj=project)
    assert result.exit_code != 0

    result = invoke(["config", "-l", "cache_dir", "/path/to/bar"], obj=project)
    assert result.exit_code != 0


def test_config_del_command(project, invoke):
    result = invoke(["config", "-l", "python.use_pyenv", "false"], obj=project)
    assert result.exit_code == 0

    result = invoke(["config", "python.use_pyenv"], obj=project)
    assert result.output.strip() == "False"

    result = invoke(["config", "-ld", "python.use_pyenv"], obj=project)
    assert result.exit_code == 0

    result = invoke(["config", "python.use_pyenv"], obj=project)
    assert result.output.strip() == "True"


def test_config_env_var_shadowing(project, invoke, monkeypatch):
    monkeypatch.setenv("PDM_PYPI_URL", "https://example.org/simple")
    result = invoke(["config", "pypi.url"], obj=project)
    assert result.output.strip() == "https://example.org/simple"

    result = invoke(["config", "pypi.url", "https://test.pypi.org/pypi"], obj=project)
    assert "config is shadowed by env var 'PDM_PYPI_URL'" in result.output
    result = invoke(["config", "pypi.url"], obj=project)
    assert result.output.strip() == "https://example.org/simple"

    monkeypatch.delenv("PDM_PYPI_URL")
    result = invoke(["config", "pypi.url"], obj=project)
    assert result.output.strip() == "https://test.pypi.org/pypi"


def test_config_project_global_precedence(project, invoke):
    invoke(["config", "python.path", "/path/to/foo"], obj=project)
    invoke(["config", "-l", "python.path", "/path/to/bar"], obj=project)

    result = invoke(["config", "python.path"], obj=project)
    assert result.output.strip() == "/path/to/bar"


def test_specify_config_file(tmp_path, invoke, monkeypatch):
    tmp_path.joinpath("global_config.toml").write_text("project_max_depth = 9\n")
    with cd(tmp_path):
        result = invoke(["-c", "global_config.toml", "config", "project_max_depth"])
        assert result.exit_code == 0
        assert result.output.strip() == "9"

        monkeypatch.setenv("PDM_CONFIG_FILE", "global_config.toml")
        result = invoke(["config", "project_max_depth"])
        assert result.exit_code == 0
        assert result.output.strip() == "9"


def test_default_repository_setting(project):
    repository = project.global_config.get_repository_config("pypi")
    assert repository.url == "https://upload.pypi.org/legacy/"
    assert repository.username is None
    assert repository.password is None

    repository = project.global_config.get_repository_config("testpypi")
    assert repository.url == "https://test.pypi.org/legacy/"

    repository = project.global_config.get_repository_config("nonexist")
    assert repository is None


def test_repository_config_not_available_on_project(project):
    with pytest.raises(PdmUsageError):
        project.project_config.get_repository_config("pypi")


def test_repository_config_key_short(project):
    with pytest.raises(PdmUsageError):
        project.global_config["repository.test"] = {"url": "https://example.org/simple"}

    with pytest.raises(PdmUsageError):
        project.global_config["repository"] = "123"

    with pytest.raises(PdmUsageError):
        del project.global_config["repository"]


def test_repository_overwrite_default(project):
    project.global_config["repository.pypi.username"] = "foo"
    project.global_config["repository.pypi.password"] = "bar"
    repository = project.global_config.get_repository_config("pypi")
    assert repository.url == "https://upload.pypi.org/legacy/"
    assert repository.username == "foo"
    assert repository.password == "bar"

    project.global_config["repository.pypi.url"] = "https://example.pypi.org/legacy/"
    repository = project.global_config.get_repository_config("pypi")
    assert repository.url == "https://example.pypi.org/legacy/"


def test_hide_password_in_output_repository(project, invoke):
    assert project.global_config["repository.pypi.password"] is None
    project.global_config["repository.pypi.username"] = "testuser"
    project.global_config["repository.pypi.password"] = "secret"
    result = invoke(["config", "repository.pypi"], obj=project, strict=True)
    assert "password = <hidden>" in result.output
    result = invoke(["config", "repository.pypi.password"], obj=project, strict=True)
    assert "<hidden>" == result.output.strip()


def test_hide_password_in_output_pypi(project, invoke):
    with pytest.raises(KeyError):
        assert project.global_config["pypi.extra.password"] is None
    project.global_config["pypi.extra.username"] = "testuser"
    project.global_config["pypi.extra.password"] = "secret"
    project.global_config["pypi.extra.url"] = "https://test/simple"
    result = invoke(["config", "pypi.extra"], obj=project, strict=True)
    assert "password = <hidden>" in result.output
    result = invoke(["config", "pypi.extra.password"], obj=project, strict=True)
    assert "<hidden>" == result.output.strip()
    result = invoke(["config"], obj=project)
    assert "pypi.extra.password" in result.output
    assert "<hidden>" in result.output


def test_config_get_repository(project, invoke):
    config = project.global_config["repository.pypi"]
    assert config == project.global_config.get_repository_config("pypi")
    assert project.global_config["repository.pypi.url"] == "https://upload.pypi.org/legacy/"

    result = invoke(["config", "repository.pypi"], obj=project, strict=True)
    assert result.stdout.strip() == "url = https://upload.pypi.org/legacy/"

    assert (
        project.global_config.get_repository_config("https://example.pypi.org/legacy/").url
        == "https://example.pypi.org/legacy/"
    )

    result = invoke(["config", "repository.pypi.url"], obj=project, strict=True)
    assert result.stdout.strip() == "https://upload.pypi.org/legacy/"


def test_config_set_repository(project):
    project.global_config["repository.pypi.url"] = "https://example.pypi.org/legacy/"
    project.global_config["repository.pypi.username"] = "foo"
    assert project.global_config["repository.pypi.url"] == "https://example.pypi.org/legacy/"
    assert project.global_config["repository.pypi.username"] == "foo"
    del project.global_config["repository.pypi.username"]
    assert project.global_config["repository.pypi.username"] is None


def test_config_del_repository(project):
    project.global_config["repository.test.url"] = "https://example.org/simple"
    assert project.global_config.get_repository_config("test") is not None

    del project.global_config["repository.test"]
    assert project.global_config.get_repository_config("test") is None
