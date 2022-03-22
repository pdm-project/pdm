import os

import pytest

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


def test_config_env_var_shadowing(project, invoke):
    os.environ["PDM_PYPI_URL"] = "https://example.org/simple"
    result = invoke(["config", "pypi.url"], obj=project)
    assert result.output.strip() == "https://example.org/simple"

    result = invoke(["config", "pypi.url", "https://test.pypi.org/pypi"], obj=project)
    assert "config is shadowed by env var 'PDM_PYPI_URL'" in result.output
    result = invoke(["config", "pypi.url"], obj=project)
    assert result.output.strip() == "https://example.org/simple"

    del os.environ["PDM_PYPI_URL"]
    result = invoke(["config", "pypi.url"], obj=project)
    assert result.output.strip() == "https://test.pypi.org/pypi"


def test_config_project_global_precedence(project, invoke):
    invoke(["config", "python.path", "/path/to/foo"], obj=project)
    invoke(["config", "-l", "python.path", "/path/to/bar"], obj=project)

    result = invoke(["config", "python.path"], obj=project)
    assert result.output.strip() == "/path/to/bar"


@pytest.mark.deprecated
def test_deprecated_config_name(project, invoke):
    result = invoke(["config", "use_venv", "true"], obj=project)
    assert result.exit_code == 0
    assert "DEPRECATED: the config has been renamed to python.use_venv" in result.stderr

    assert project.config["python.use_venv"] is True


@pytest.mark.deprecated
@pytest.mark.usefixtures("project")
def test_rename_deprected_config(tmp_path, invoke):
    tmp_path.joinpath(".pdm.toml").write_text("use_venv = true\n")
    with cd(tmp_path):
        result = invoke(["config"])
        assert result.exit_code == 0
        assert "python.use_venv(deprecating: use_venv)" in result.output

        result = invoke(["config", "-l", "python.use_venv", "true"])
        assert result.exit_code == 0
        assert (
            tmp_path.joinpath(".pdm.toml").read_text().strip()
            == "[python]\nuse_venv = true"
        )


def test_specify_config_file(tmp_path, invoke):
    tmp_path.joinpath("global_config.toml").write_text("project_max_depth = 9\n")
    with cd(tmp_path):
        result = invoke(["-c", "global_config.toml", "config", "project_max_depth"])
        assert result.exit_code == 0
        assert result.output.strip() == "9"

        os.environ["PDM_CONFIG_FILE"] = "global_config.toml"
        result = invoke(["config", "project_max_depth"])
        assert result.exit_code == 0
        assert result.output.strip() == "9"
