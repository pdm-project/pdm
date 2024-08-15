import pytest

from pdm.exceptions import PdmUsageError
from pdm.utils import cd


def test_config_command(project, pdm):
    result = pdm(["config"], obj=project)
    assert result.exit_code == 0
    assert "python.use_pyenv = True" in result.output

    result = pdm(["config", "-v"], obj=project)
    assert result.exit_code == 0
    assert "Use the pyenv interpreter" in result.output


def test_config_get_command(project, pdm):
    result = pdm(["config", "python.use_pyenv"], obj=project)
    assert result.exit_code == 0
    assert result.output.strip() == "True"

    result = pdm(["config", "foo.bar"], obj=project)
    assert result.exit_code != 0


def test_config_set_command(project, pdm):
    result = pdm(["config", "python.use_pyenv", "false"], obj=project)
    assert result.exit_code == 0
    result = pdm(["config", "python.use_pyenv"], obj=project)
    assert result.output.strip() == "False"

    result = pdm(["config", "foo.bar"], obj=project)
    assert result.exit_code != 0

    result = pdm(["config", "-l", "cache_dir", "/path/to/bar"], obj=project)
    assert result.exit_code != 0


def test_config_del_command(project, pdm):
    result = pdm(["config", "-l", "python.use_pyenv", "false"], obj=project)
    assert result.exit_code == 0

    result = pdm(["config", "python.use_pyenv"], obj=project)
    assert result.output.strip() == "False"

    result = pdm(["config", "-ld", "python.use_pyenv"], obj=project)
    assert result.exit_code == 0

    result = pdm(["config", "python.use_pyenv"], obj=project)
    assert result.output.strip() == "True"


def test_config_env_var_shadowing(project, pdm, monkeypatch):
    monkeypatch.setenv("PDM_PYPI_URL", "https://example.org/simple")
    result = pdm(["config", "pypi.url"], obj=project)
    assert result.output.strip() == "https://example.org/simple"

    result = pdm(["config", "pypi.url", "https://test.pypi.org/pypi"], obj=project)
    assert "config is shadowed by env var 'PDM_PYPI_URL'" in result.stderr
    result = pdm(["config", "pypi.url"], obj=project)
    assert result.output.strip() == "https://example.org/simple"

    monkeypatch.delenv("PDM_PYPI_URL")
    result = pdm(["config", "pypi.url"], obj=project)
    assert result.output.strip() == "https://test.pypi.org/pypi"


def test_config_project_global_precedence(project, pdm):
    pdm(["config", "python.use_pyenv", "true"], obj=project)
    pdm(["config", "-l", "python.use_pyenv", "false"], obj=project)

    result = pdm(["config", "python.use_pyenv"], obj=project)
    assert result.output.strip() == "False"


def test_specify_config_file(tmp_path, pdm, monkeypatch):
    tmp_path.joinpath("global_config.toml").write_text("strategy.resolve_max_rounds = 1000\n")
    with cd(tmp_path):
        result = pdm(["-c", "global_config.toml", "config", "strategy.resolve_max_rounds"])
        assert result.exit_code == 0
        assert result.output.strip() == "1000"

        monkeypatch.setenv("PDM_CONFIG_FILE", "global_config.toml")
        result = pdm(["config", "strategy.resolve_max_rounds"])
        assert result.exit_code == 0
        assert result.output.strip() == "1000"


def test_default_repository_setting(project):
    repository = project.global_config.get_repository_config("pypi", "repository")
    assert repository.url == "https://upload.pypi.org/legacy/"
    assert repository.username is None
    assert repository.password is None

    repository = project.global_config.get_repository_config("testpypi", "repository")
    assert repository.url == "https://test.pypi.org/legacy/"

    repository = project.global_config.get_repository_config("nonexist", "repository")
    assert repository is None


def test_repository_config_not_available_on_project(project):
    with pytest.raises(PdmUsageError):
        project.project_config.get_repository_config("pypi", "repository")


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
    repository = project.global_config.get_repository_config("pypi", "repository")
    assert repository.url == "https://upload.pypi.org/legacy/"
    assert repository.username == "foo"
    assert repository.password == "bar"

    project.global_config["repository.pypi.url"] = "https://example.pypi.org/legacy/"
    repository = project.global_config.get_repository_config("pypi", "repository")
    assert repository.url == "https://example.pypi.org/legacy/"


def test_hide_password_in_output_repository(project, pdm):
    assert project.global_config["repository.pypi.password"] is None
    project.global_config["repository.pypi.username"] = "testuser"
    project.global_config["repository.pypi.password"] = "secret"
    result = pdm(["config", "repository.pypi"], obj=project, strict=True)
    assert "password = <hidden>" in result.output
    result = pdm(["config", "repository.pypi.password"], obj=project, strict=True)
    assert "<hidden>" == result.output.strip()


def test_hide_password_in_output_pypi(project, pdm):
    with pytest.raises(KeyError):
        assert project.global_config["pypi.extra.password"] is None
    project.global_config["pypi.extra.username"] = "testuser"
    project.global_config["pypi.extra.password"] = "secret"
    project.global_config["pypi.extra.url"] = "https://test/simple"
    result = pdm(["config", "pypi.extra"], obj=project, strict=True)
    assert "password = <hidden>" in result.output
    result = pdm(["config", "pypi.extra.password"], obj=project, strict=True)
    assert "<hidden>" == result.output.strip()
    result = pdm(["config"], obj=project)
    assert "pypi.extra.password" in result.output
    assert "<hidden>" in result.output


def test_config_get_repository(project, pdm):
    config = project.global_config["repository.pypi"]
    assert config == project.global_config.get_repository_config("pypi", "repository")
    assert project.global_config["repository.pypi.url"] == "https://upload.pypi.org/legacy/"

    result = pdm(["config", "repository.pypi"], obj=project, strict=True)
    assert result.stdout.strip() == "repository.pypi.url = https://upload.pypi.org/legacy/"

    assert (
        project.global_config.get_repository_config("https://example.pypi.org/legacy/", "repository").url
        == "https://example.pypi.org/legacy/"
    )

    result = pdm(["config", "repository.pypi.url"], obj=project, strict=True)
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
    assert project.global_config.get_repository_config("test", "repository") is not None

    del project.global_config["repository.test"]
    assert project.global_config.get_repository_config("test", "repository") is None


def test_config_password_save_into_keyring(project, keyring):
    project.global_config.update(
        {
            "pypi.extra.url": "https://extra.pypi.org/simple",
            "pypi.extra.username": "foo",
            "pypi.extra.password": "barbaz",
            "repository.pypi.username": "frost",
            "repository.pypi.password": "password",
        }
    )

    assert project.global_config["pypi.extra.password"] == "barbaz"
    assert project.global_config["repository.pypi.password"] == "password"
    for key in ("pypi.extra", "repository.pypi"):
        assert "password" not in project.global_config._file_data[key]

    assert keyring.enabled
    assert keyring.get_auth_info("pdm-pypi-extra", "foo") == ("foo", "barbaz")
    assert keyring.get_auth_info("pdm-repository-pypi", None) == ("frost", "password")

    del project.global_config["pypi.extra"]
    del project.global_config["repository.pypi.password"]
    assert keyring.get_auth_info("pdm-pypi-extra", "foo") is None
    assert keyring.get_auth_info("pdm-repository-pypi", None) is None


def test_keyring_operation_error_disables_itself(project, keyring, mocker):
    saver = mocker.patch.object(keyring.provider, "save_auth_info", side_effect=RuntimeError())
    getter = mocker.patch.object(keyring.provider, "get_auth_info")
    project.global_config.update(
        {
            "pypi.extra.url": "https://extra.pypi.org/simple",
            "pypi.extra.username": "foo",
            "pypi.extra.password": "barbaz",
            "repository.pypi.username": "frost",
            "repository.pypi.password": "password",
        }
    )

    assert project.global_config["pypi.extra.password"] == "barbaz"
    assert project.global_config["repository.pypi.password"] == "password"

    saver.assert_called_once()
    getter.assert_not_called()

    assert not keyring.enabled
    assert keyring.get_auth_info("pdm-pypi-extra", "foo") is None
    assert keyring.get_auth_info("pdm-repository-pypi", None) is None
