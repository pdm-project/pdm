import os
import shutil
import sys
from pathlib import Path
from typing import Callable

import pytest
from pytest_mock.plugin import MockerFixture

from pdm.cli import actions
from pdm.models.in_process import get_python_version
from pdm.models.requirements import parse_requirement
from pdm.utils import temp_environ
from tests import FIXTURES
from tests.conftest import MockWorkingSet, TestProject, TestRepository


def test_help_option(invoke: Callable) -> None:
    result = invoke(["--help"])
    assert "PDM - Python Development Master" in result.output


def test_lock_command(
    project: TestProject, invoke: Callable, mocker: MockerFixture
) -> None:
    m = mocker.patch.object(actions, "do_lock")
    invoke(["lock"], obj=project)
    m.assert_called_with(project)


def test_install_command(
    project: TestProject, invoke: Callable, mocker: MockerFixture
) -> None:
    do_lock = mocker.patch.object(actions, "do_lock")
    do_sync = mocker.patch.object(actions, "do_sync")
    invoke(["install"], obj=project)
    do_lock.assert_called_once()
    do_sync.assert_called_once()


def test_sync_command(
    project: TestProject, invoke: Callable, mocker: MockerFixture
) -> None:
    do_sync = mocker.patch.object(actions, "do_sync")
    invoke(["sync"], obj=project)
    do_sync.assert_called_once()


def test_update_command(
    project: TestProject, invoke: Callable, mocker: MockerFixture
) -> None:
    do_update = mocker.patch.object(actions, "do_update")
    invoke(["update"], obj=project)
    do_update.assert_called_once()


def test_remove_command(
    project: TestProject, invoke: Callable, mocker: MockerFixture
) -> None:
    do_remove = mocker.patch.object(actions, "do_remove")
    invoke(["remove", "demo"], obj=project)
    do_remove.assert_called_once()


def test_add_command(
    project: TestProject, invoke: Callable, mocker: MockerFixture
) -> None:
    do_add = mocker.patch.object(actions, "do_add")
    invoke(["add", "requests"], obj=project)
    do_add.assert_called_once()


def test_build_command(
    project: TestProject, invoke: Callable, mocker: MockerFixture
) -> None:
    do_build = mocker.patch.object(actions, "do_build")
    invoke(["build"], obj=project)
    do_build.assert_called_once()


def test_build_global_project_forbidden(invoke: Callable) -> None:
    result = invoke(["build", "-g"])
    assert result.exit_code != 0


def test_list_command(
    project: TestProject, invoke: Callable, mocker: MockerFixture
) -> None:
    do_list = mocker.patch.object(actions, "do_list")
    invoke(["list"], obj=project)
    do_list.assert_called_once()


def test_info_command(project: TestProject, invoke: Callable) -> None:
    result = invoke(["info"], obj=project)
    assert "Project Root:" in result.output
    assert project.root.as_posix() in result.output

    result = invoke(["info", "--python"], obj=project)
    assert result.output.strip() == project.python_executable

    result = invoke(["info", "--where"], obj=project)
    assert result.output.strip() == project.root.as_posix()

    result = invoke(["info", "--env"], obj=project)
    assert result.exit_code == 0


def test_info_global_project(invoke: Callable) -> None:
    result = invoke(["info", "-g", "--where"])
    assert "global-project" in result.output.strip()


def test_deprecate_global_project(invoke: Callable, project: TestProject) -> None:
    result = invoke(["info", "-g", project.root.as_posix()])
    assert "DEPRECATION" in result.stderr


def test_global_project_other_location(invoke: Callable, project: TestProject) -> None:
    result = invoke(["info", "-g", "-p", project.root.as_posix(), "--where"])
    assert result.stdout.strip() == project.root.as_posix()


def test_uncaught_error(invoke: Callable, mocker: MockerFixture) -> None:
    mocker.patch.object(actions, "do_list", side_effect=RuntimeError("test error"))
    result = invoke(["list"])
    assert "[RuntimeError]: test error" in result.stderr

    result = invoke(["list", "-v"])
    assert isinstance(result.exception, RuntimeError)


def test_use_command(project: TestProject, invoke: Callable) -> None:
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


def test_use_python_by_version(project: TestProject, invoke: Callable) -> None:
    python_version = ".".join(map(str, sys.version_info[:2]))
    result = invoke(["use", "-f", python_version], obj=project)
    assert result.exit_code == 0


def test_install_with_lockfile(
    project: TestProject,
    invoke: Callable,
    working_set: MockWorkingSet,
    repository: TestRepository,
) -> None:
    result = invoke(["lock", "-v"], obj=project)
    assert result.exit_code == 0
    result = invoke(["install"], obj=project)
    assert "Lock file" not in result.output

    project.add_dependencies({"pytz": parse_requirement("pytz")})
    result = invoke(["install"], obj=project)
    assert "Lock file hash doesn't match" in result.output
    assert "pytz" in project.get_locked_candidates()
    assert project.is_lockfile_hash_match()


def test_init_command(
    project_no_init: TestProject, invoke: Callable, mocker: MockerFixture
) -> None:
    mocker.patch(
        "pdm.cli.commands.init.get_user_email_from_git",
        return_value=("Testing", "me@example.org"),
    )
    do_init = mocker.patch.object(actions, "do_init")
    result = invoke(["init"], input="\n\n\n\n\n\n", obj=project_no_init)
    assert result.exit_code == 0
    python_version, _ = get_python_version(project_no_init.python_executable, True, 2)
    do_init.assert_called_with(
        project_no_init,
        "",
        "",
        "MIT",
        "Testing",
        "me@example.org",
        f">={python_version}",
    )


def test_init_command_library(
    project_no_init: TestProject, invoke: Callable, mocker: MockerFixture
) -> None:
    mocker.patch(
        "pdm.cli.commands.init.get_user_email_from_git",
        return_value=("Testing", "me@example.org"),
    )
    do_init = mocker.patch.object(actions, "do_init")
    result = invoke(
        ["init"], input="\ny\ntest-project\n\n\n\n\n\n", obj=project_no_init
    )
    assert result.exit_code == 0
    python_version, _ = get_python_version(project_no_init.python_executable, True, 2)
    do_init.assert_called_with(
        project_no_init,
        "test-project",
        "0.1.0",
        "MIT",
        "Testing",
        "me@example.org",
        f">={python_version}",
    )


def test_config_command(project: TestProject, invoke: Callable) -> None:
    result = invoke(["config"], obj=project)
    assert result.exit_code == 0
    assert "python.use_pyenv = True" in result.output

    result = invoke(["config", "-v"], obj=project)
    assert result.exit_code == 0
    assert "Use the pyenv interpreter" in result.output


def test_config_get_command(project: TestProject, invoke: Callable) -> None:
    result = invoke(["config", "python.use_pyenv"], obj=project)
    assert result.exit_code == 0
    assert result.output.strip() == "True"

    result = invoke(["config", "foo.bar"], obj=project)
    assert result.exit_code != 0


def test_config_set_command(project: TestProject, invoke: Callable) -> None:
    result = invoke(["config", "python.use_pyenv", "false"], obj=project)
    assert result.exit_code == 0
    result = invoke(["config", "python.use_pyenv"], obj=project)
    assert result.output.strip() == "False"

    result = invoke(["config", "foo.bar"], obj=project)
    assert result.exit_code != 0

    result = invoke(["config", "-l", "cache_dir", "/path/to/bar"], obj=project)
    assert result.exit_code != 0


def test_config_env_var_shadowing(project: TestProject, invoke: Callable) -> None:
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


def test_config_project_global_precedence(
    project: TestProject, invoke: Callable
) -> None:
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
def test_import_other_format_file(
    project: TestProject, invoke: Callable, filename: str
) -> None:
    requirements_file = FIXTURES / filename
    result = invoke(["import", str(requirements_file)], obj=project)
    assert result.exit_code == 0


@pytest.mark.pypi
def test_search_package(project: TestProject, invoke: Callable) -> None:
    result = invoke(["search", "requests"], obj=project)
    assert result.exit_code == 0
    assert len(result.output.splitlines()) > 0


@pytest.mark.pypi
def test_show_package_on_pypi(invoke: Callable) -> None:
    result = invoke(["show", "ipython"])
    assert result.exit_code == 0
    assert "ipython" in result.output.splitlines()[0]

    result = invoke(["show", "requests"])
    assert result.exit_code == 0
    assert "requests" in result.output.splitlines()[0]


def test_export_to_requirements_txt(
    invoke: Callable, fixture_project: Callable
) -> None:
    project = fixture_project("demo-package")
    requirements_txt = project.root / "requirements.txt"
    requirements_no_hashes = project.root / "requirements_simple.txt"
    requirements_pyproject = project.root / "requirements.ini"

    result = invoke(["export"], obj=project)
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


def test_completion_command(invoke: Callable) -> None:
    result = invoke(["completion", "bash"])
    assert result.exit_code == 0
    assert "(completion)" in result.output


def test_lock_legacy_project(
    invoke: Callable, fixture_project: Callable, repository: TestRepository
) -> None:
    project = fixture_project("demo-legacy")
    result = invoke(["lock"], obj=project)
    assert result.exit_code == 0
    assert "urllib3" in project.get_locked_candidates()
