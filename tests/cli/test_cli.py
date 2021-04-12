import os
import shutil
import sys
from pathlib import Path

import pytest

from pdm.cli import actions
from pdm.models.requirements import parse_requirement
from pdm.utils import cd, temp_environ
from tests import FIXTURES


def test_help_option(invoke):
    result = invoke(["--help"])
    assert "PDM - Python Development Master" in result.output


def test_lock_command(project, invoke, mocker):
    m = mocker.patch.object(actions, "do_lock")
    invoke(["lock"], obj=project)
    m.assert_called_with(project)


def test_install_command(project, invoke, mocker):
    do_lock = mocker.patch.object(actions, "do_lock")
    do_sync = mocker.patch.object(actions, "do_sync")
    invoke(["install"], obj=project)
    do_lock.assert_called_once()
    do_sync.assert_called_once()


def test_sync_command(project, invoke, mocker):
    do_sync = mocker.patch.object(actions, "do_sync")
    invoke(["sync"], obj=project)
    do_sync.assert_called_once()


def test_update_command(project, invoke, mocker):
    do_update = mocker.patch.object(actions, "do_update")
    invoke(["update"], obj=project)
    do_update.assert_called_once()


def test_remove_command(project, invoke, mocker):
    do_remove = mocker.patch.object(actions, "do_remove")
    invoke(["remove", "demo"], obj=project)
    do_remove.assert_called_once()


def test_add_command(project, invoke, mocker):
    do_add = mocker.patch.object(actions, "do_add")
    invoke(["add", "requests"], obj=project)
    do_add.assert_called_once()


def test_build_command(project, invoke, mocker):
    do_build = mocker.patch.object(actions, "do_build")
    invoke(["build"], obj=project)
    do_build.assert_called_once()


def test_build_global_project_forbidden(invoke):
    result = invoke(["build", "-g"])
    assert result.exit_code != 0


def test_list_command(project, invoke, mocker):
    do_list = mocker.patch.object(actions, "do_list")
    invoke(["list"], obj=project)
    do_list.assert_called_once()


def test_info_command(project, invoke):
    result = invoke(["info"], obj=project)
    assert "Project Root:" in result.output
    assert project.root.as_posix() in result.output

    result = invoke(["info", "--python"], obj=project)
    assert result.output.strip() == project.python.executable

    result = invoke(["info", "--where"], obj=project)
    assert result.output.strip() == project.root.as_posix()

    result = invoke(["info", "--env"], obj=project)
    assert result.exit_code == 0


def test_info_global_project(invoke, tmp_path):
    with cd(tmp_path):
        result = invoke(["info", "-g", "--where"])
    assert "global-project" in result.output.strip()


def test_global_project_other_location(invoke, project):
    result = invoke(["info", "-g", "-p", project.root.as_posix(), "--where"])
    assert result.stdout.strip() == project.root.as_posix()


def test_uncaught_error(invoke, mocker):
    mocker.patch.object(actions, "do_list", side_effect=RuntimeError("test error"))
    result = invoke(["list"])
    assert "[RuntimeError]: test error" in result.stderr

    result = invoke(["list", "-v"])
    assert isinstance(result.exception, RuntimeError)


def test_use_command(project, invoke):
    python_path = Path(shutil.which("python")).as_posix()
    result = invoke(["use", "-f", "python"], obj=project)
    assert result.exit_code == 0
    config_content = project.root.joinpath(".pdm.toml").read_text()
    assert python_path in config_content

    result = invoke(["use", "-f", python_path], obj=project)
    assert result.exit_code == 0

    project.meta["requires-python"] = ">=3.6"
    project.write_pyproject()
    result = invoke(["use", "2.7"], obj=project)
    assert result.exit_code == 1


def test_use_python_by_version(project, invoke):
    python_version = ".".join(map(str, sys.version_info[:2]))
    result = invoke(["use", "-f", python_version], obj=project)
    assert result.exit_code == 0


def test_install_with_lockfile(project, invoke, working_set, repository):
    result = invoke(["lock", "-v"], obj=project)
    assert result.exit_code == 0
    result = invoke(["install"], obj=project)
    assert "Lock file" not in result.output

    project.add_dependencies({"pytz": parse_requirement("pytz")}, "default")
    result = invoke(["install"], obj=project)
    assert "Lock file hash doesn't match" in result.output
    assert "pytz" in project.get_locked_candidates()
    assert project.is_lockfile_hash_match()


def test_init_command(project_no_init, invoke, mocker):
    mocker.patch(
        "pdm.cli.commands.init.get_user_email_from_git",
        return_value=("Testing", "me@example.org"),
    )
    do_init = mocker.patch.object(actions, "do_init")
    result = invoke(["init"], input="\n\n\n\n\n\n", obj=project_no_init)
    assert result.exit_code == 0
    python_version = f"{project_no_init.python.major}.{project_no_init.python.minor}"
    do_init.assert_called_with(
        project_no_init,
        "",
        "",
        "MIT",
        "Testing",
        "me@example.org",
        f">={python_version}",
    )


def test_init_command_library(project_no_init, invoke, mocker):
    mocker.patch(
        "pdm.cli.commands.init.get_user_email_from_git",
        return_value=("Testing", "me@example.org"),
    )
    do_init = mocker.patch.object(actions, "do_init")
    result = invoke(
        ["init"], input="\ny\ntest-project\n\n\n\n\n\n", obj=project_no_init
    )
    assert result.exit_code == 0
    python_version = f"{project_no_init.python.major}.{project_no_init.python.minor}"
    do_init.assert_called_with(
        project_no_init,
        "test-project",
        "0.1.0",
        "MIT",
        "Testing",
        "me@example.org",
        f">={python_version}",
    )


def test_init_non_interactive(project_no_init, invoke, mocker):
    mocker.patch(
        "pdm.cli.commands.init.get_user_email_from_git",
        return_value=("Testing", "me@example.org"),
    )
    do_init = mocker.patch.object(actions, "do_init")
    result = invoke(["init", "-n"], obj=project_no_init)
    assert result.exit_code == 0
    python_version = f"{project_no_init.python.major}.{project_no_init.python.minor}"
    do_init.assert_called_with(
        project_no_init,
        "",
        "",
        "MIT",
        "Testing",
        "me@example.org",
        f">={python_version}",
    )


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
    with temp_environ():
        os.environ["PDM_PYPI_URL"] = "https://example.org/simple"
        result = invoke(["config", "pypi.url"], obj=project)
        assert result.output.strip() == "https://example.org/simple"

        result = invoke(
            ["config", "pypi.url", "https://testpypi.org/pypi"], obj=project
        )
        assert "config is shadowed by env var 'PDM_PYPI_URL'" in result.output
        result = invoke(["config", "pypi.url"], obj=project)
        assert result.output.strip() == "https://example.org/simple"

        del os.environ["PDM_PYPI_URL"]
        result = invoke(["config", "pypi.url"], obj=project)
        assert result.output.strip() == "https://testpypi.org/pypi"


def test_config_project_global_precedence(project, invoke):
    invoke(["config", "python.path", "/path/to/foo"], obj=project)
    invoke(["config", "-l", "python.path", "/path/to/bar"], obj=project)

    result = invoke(["config", "python.path"], obj=project)
    assert result.output.strip() == "/path/to/bar"


@pytest.mark.parametrize(
    "filename",
    [
        "requirements.txt",
        "Pipfile",
        "pyproject-poetry.toml",
        "projects/flit-demo/pyproject.toml",
    ],
)
def test_import_other_format_file(project, invoke, filename):
    requirements_file = FIXTURES / filename
    result = invoke(["import", str(requirements_file)], obj=project)
    assert result.exit_code == 0


def test_import_requirement_no_overwrite(project, invoke, tmp_path):
    project.add_dependencies({"requests": parse_requirement("requests")})
    tmp_path.joinpath("reqs.txt").write_text("flask\nflask-login\n")
    result = invoke(
        ["import", "-dsweb", str(tmp_path.joinpath("reqs.txt"))], obj=project
    )
    assert result.exit_code == 0, result.stderr
    assert list(project.get_dependencies()) == ["requests"]
    assert list(project.get_dependencies("web")) == ["flask", "flask-login"]


@pytest.mark.pypi
def test_search_package(project, invoke):
    result = invoke(["search", "requests"], obj=project)
    assert result.exit_code == 0
    assert len(result.output.splitlines()) > 0


@pytest.mark.pypi
def test_show_package_on_pypi(invoke):
    result = invoke(["show", "ipython"])
    assert result.exit_code == 0
    assert "ipython" in result.output.splitlines()[0]

    result = invoke(["show", "requests"])
    assert result.exit_code == 0
    assert "requests" in result.output.splitlines()[0]


def test_export_to_requirements_txt(invoke, fixture_project):
    project = fixture_project("demo-package")
    requirements_txt = project.root / "requirements.txt"
    requirements_no_hashes = project.root / "requirements_simple.txt"
    requirements_pyproject = project.root / "requirements.ini"

    result = invoke(["export"], obj=project)
    print("==========OUTPUT=============", result.output.strip(), result.stderr.strip())
    assert result.exit_code == 0
    assert result.output.strip() == requirements_txt.read_text().strip()

    result = invoke(["export", "--without-hashes"], obj=project)
    assert result.exit_code == 0
    assert result.output.strip() == requirements_no_hashes.read_text().strip()

    result = invoke(["export", "--pyproject"], obj=project)
    assert result.exit_code == 0
    assert result.output.strip() == requirements_pyproject.read_text().strip()

    result = invoke(
        ["export", "-o", str(project.root / "requirements_output.txt")], obj=project
    )
    assert result.exit_code == 0
    assert (
        project.root / "requirements_output.txt"
    ).read_text() == requirements_txt.read_text()


def test_completion_command(invoke):
    result = invoke(["completion", "bash"])
    assert result.exit_code == 0
    assert "(completion)" in result.output


def test_lock_legacy_project(invoke, fixture_project, repository):
    project = fixture_project("demo-legacy")
    result = invoke(["lock"], obj=project)
    assert result.exit_code == 0
    assert "urllib3" in project.get_locked_candidates()
