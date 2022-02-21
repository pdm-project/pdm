import pytest

from pdm.cli import actions
from pdm.exceptions import PdmException
from pdm.models.requirements import parse_requirement
from pdm.utils import cd
from tests import FIXTURES


@pytest.mark.usefixtures("repository")
def test_lock_dependencies(project):
    project.add_dependencies({"requests": parse_requirement("requests")})
    actions.do_lock(project)
    assert project.lockfile_file.exists()
    locked = project.locked_repository.all_candidates
    for package in ("requests", "idna", "chardet", "certifi"):
        assert package in locked


@pytest.mark.usefixtures("project_no_init", "local_finder")
def test_build_distributions(tmp_path, core):
    project = core.create_project()
    actions.do_build(project, dest=tmp_path.as_posix())
    wheel = next(tmp_path.glob("*.whl"))
    assert wheel.name.startswith("pdm-")
    tarball = next(tmp_path.glob("*.tar.gz"))
    assert tarball.exists()


def test_project_no_init_error(project_no_init):

    for handler in (
        actions.do_add,
        actions.do_list,
        actions.do_lock,
        actions.do_update,
    ):
        with pytest.raises(
            PdmException, match="The pyproject.toml has not been initialized yet"
        ):
            handler(project_no_init)


def test_init_validate_python_requires(project_no_init):
    with pytest.raises(ValueError):
        actions.do_init(project_no_init, python_requires="3.7")


def test_help_option(invoke):
    result = invoke(["--help"])
    assert "PDM - Python Development Master" in result.output


def test_lock_command(project, invoke, mocker):
    m = mocker.patch.object(actions, "do_lock")
    invoke(["lock"], obj=project)
    m.assert_called_with(project, refresh=False)


def test_info_command(project, invoke):
    result = invoke(["info"], obj=project)
    assert "Project Root:" in result.output
    assert project.root.as_posix() in result.output

    result = invoke(["info", "--python"], obj=project)
    assert result.output.strip() == str(project.python.executable)

    result = invoke(["info", "--where"], obj=project)
    assert result.output.strip() == str(project.root)

    result = invoke(["info", "--env"], obj=project)
    assert result.exit_code == 0


def test_info_global_project(invoke, tmp_path):
    with cd(tmp_path):
        result = invoke(["info", "-g", "--where"])
    assert "global-project" in result.output.strip()


def test_global_project_other_location(invoke, project):
    result = invoke(["info", "-g", "-p", project.root.as_posix(), "--where"])
    assert result.stdout.strip() == str(project.root)


def test_uncaught_error(invoke, mocker):
    mocker.patch.object(actions, "do_list", side_effect=RuntimeError("test error"))
    result = invoke(["list"])
    assert "[RuntimeError]: test error" in result.stderr

    result = invoke(["list", "-v"])
    assert isinstance(result.exception, RuntimeError)


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
        ["import", "-dGweb", str(tmp_path.joinpath("reqs.txt"))], obj=project
    )
    assert result.exit_code == 0, result.stderr
    assert list(project.get_dependencies()) == ["requests"]
    assert list(project.get_dependencies("web")) == ["flask", "flask-login"]


@pytest.mark.network
def test_search_package(invoke):
    result = invoke(["search", "requests"])
    assert result.exit_code == 0
    assert len(result.output.splitlines()) > 0


@pytest.mark.network
def test_show_package_on_pypi(invoke):
    result = invoke(["show", "ipython"])
    assert result.exit_code == 0
    assert "ipython" in result.output.splitlines()[0]

    result = invoke(["show", "requests"])
    assert result.exit_code == 0
    assert "requests" in result.output.splitlines()[0]

    result = invoke(["show", "--name", "requests"])
    assert result.exit_code == 0
    assert "requests" in result.output.splitlines()[0]


def test_show_self_package(project, invoke):
    result = invoke(["show"], obj=project)
    assert result.exit_code == 0, result.stderr

    result = invoke(["show", "--name", "--version"], obj=project)
    assert result.exit_code == 0
    assert "test_project\n0.0.0\n" == result.output


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


def test_export_doesnt_include_dep_with_extras(invoke, fixture_project):
    project = fixture_project("demo-package-has-dep-with-extras")
    requirements_txt = project.root / "requirements.txt"

    result = invoke(["export", "--without-hashes"], obj=project)
    assert result.exit_code == 0
    assert result.output.strip() == requirements_txt.read_text().strip()


def test_completion_command(invoke):
    result = invoke(["completion", "bash"])
    assert result.exit_code == 0
    assert "(completion)" in result.output


def test_lock_refresh(invoke, project, repository):
    project.add_dependencies({"requests": parse_requirement("requests")})
    result = invoke(["lock"], obj=project)
    assert result.exit_code == 0
    assert project.is_lockfile_hash_match()
    project.add_dependencies({"requests": parse_requirement("requests>=2.0")})
    assert not project.is_lockfile_hash_match()
    result = invoke(["lock", "--refresh"], obj=project)
    assert result.exit_code == 0
    assert project.is_lockfile_hash_match()


@pytest.mark.network
def test_show_update_hint(invoke, project):
    prev_version = project.core.version
    try:
        project.core.version = "0.0.0"
        r = invoke(["config"], obj=project)
    finally:
        project.core.version = prev_version
    assert "to upgrade." in r.stderr
    assert "Run $ pdm config check_update false to disable the check." in r.stderr
