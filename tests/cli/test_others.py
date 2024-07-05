import json
from pathlib import Path

import pytest

from pdm.cli import actions
from pdm.utils import cd
from tests import FIXTURES


@pytest.mark.usefixtures("project_no_init", "local_finder")
def test_build_distributions(tmp_path, core):
    from pdm.cli.commands.build import Command

    project = core.create_project()
    Command.do_build(project, dest=tmp_path.as_posix())
    wheel = next(tmp_path.glob("*.whl"))
    assert wheel.name.startswith("pdm-")
    tarball = next(tmp_path.glob("*.tar.gz"))
    assert tarball.exists()


def test_project_no_init_error(project_no_init, pdm):
    for command in ("add", "lock", "update"):
        result = pdm([command], obj=project_no_init)
        assert result.exit_code != 0
        assert "The pyproject.toml has not been initialized yet" in result.stderr


def test_help_option(pdm):
    result = pdm(["--help"])
    assert "Usage: pdm [-h]" in result.output


def test_pep582_option(pdm):
    result = pdm(["--pep582", "bash"])
    assert result.exit_code == 0


def test_info_command(project, pdm):
    result = pdm(["info"], obj=project)
    assert "Project Root:" in result.output
    assert project.root.as_posix() in result.output

    result = pdm(["info", "--python"], obj=project)
    assert result.output.strip() == str(project.python.executable)

    result = pdm(["info", "--where"], obj=project)
    assert result.output.strip() == str(project.root)

    result = pdm(["info", "--env"], obj=project)
    assert result.exit_code == 0


def test_info_command_json(project, pdm):
    result = pdm(["info", "--json"], obj=project, strict=True)

    data = json.loads(result.outputs)

    assert data["pdm"]["version"] == project.core.version
    assert data["python"]["version"] == project.environment.interpreter.identifier
    assert data["python"]["interpreter"] == str(project.environment.interpreter.executable)
    assert isinstance(data["python"]["markers"], dict)
    assert data["project"]["root"] == str(project.root)
    assert isinstance(data["project"]["pypackages"], str)


def test_info_global_project(pdm, tmp_path):
    with cd(tmp_path):
        result = pdm(["info", "-g", "--where"])
    assert "global-project" in result.output.strip()


def test_info_with_multiple_venvs(pdm, project):
    project.global_config["python.use_venv"] = True
    pdm(["venv", "create"], obj=project, strict=True)
    pdm(["venv", "create", "--name", "test"], obj=project, strict=True)
    project._saved_python = None
    result = pdm(["info", "--python"], obj=project, strict=True)
    assert Path(result.output.strip()).parent.parent == project.root / ".venv"
    venv_location = project.config["venv.location"]
    result = pdm(["info", "--python", "--venv", "test"], obj=project, strict=True)
    assert Path(result.output.strip()).parent.parent.parent == project.root / venv_location

    result = pdm(["info", "--python", "--venv", "test"], obj=project, strict=True, env={"PDM_IN_VENV": "test"})
    assert Path(result.output.strip()).parent.parent.parent == project.root / venv_location
    result = pdm(["info", "--python", "--venv", "default"], obj=project)
    assert "No virtualenv with key 'default' is found" in result.stderr


def test_global_project_other_location(pdm, project):
    result = pdm(["info", "-g", "-p", project.root.as_posix(), "--where"])
    assert result.stdout.strip() == str(project.root)


def test_uncaught_error(pdm, mocker):
    mocker.patch.object(actions, "do_lock", side_effect=RuntimeError("test error"))
    result = pdm(["lock"])
    assert "[RuntimeError]: test error" in result.stderr

    result = pdm(["lock", "-v"])
    assert isinstance(result.exception, RuntimeError)


@pytest.mark.parametrize(
    "filename",
    [
        "requirements.txt",
        "Pipfile",
        "pyproject.toml",
        "projects/flit-demo/pyproject.toml",
    ],
)
def test_import_other_format_file(project, pdm, filename):
    requirements_file = FIXTURES / filename
    result = pdm(["import", str(requirements_file)], obj=project)
    assert result.exit_code == 0


def test_import_requirement_no_overwrite(project, pdm, tmp_path):
    project.add_dependencies(["requests"])
    tmp_path.joinpath("reqs.txt").write_text("flask\nflask-login\n")
    result = pdm(["import", "-dGweb", str(tmp_path.joinpath("reqs.txt"))], obj=project)
    assert result.exit_code == 0, result.stderr
    assert [r.key for r in project.get_dependencies()] == ["requests"]
    assert [r.key for r in project.get_dependencies("web")] == ["flask", "flask-login"]


@pytest.mark.network
def test_search_package(pdm, tmp_path):
    with cd(tmp_path):
        result = pdm(["search", "requests"])
    assert result.exit_code == 0
    assert len(result.output.splitlines()) > 0
    assert not tmp_path.joinpath("__pypackages__").exists()
    assert not tmp_path.joinpath(".pdm-python").exists()


@pytest.mark.network
def test_show_package_on_pypi(pdm):
    result = pdm(["show", "ipython"])
    assert result.exit_code == 0
    assert "ipython" in result.output.splitlines()[0]

    result = pdm(["show", "requests"])
    assert result.exit_code == 0
    assert "requests" in result.output.splitlines()[0]

    result = pdm(["show", "--name", "requests"])
    assert result.exit_code == 0
    assert "requests" in result.output.splitlines()[0]

    result = pdm(["show", "--name", "sphinx-data-viewer"])
    assert result.exit_code == 0
    assert "sphinx-data-viewer" in result.output.splitlines()[0]


def test_show_self_package(project, pdm):
    result = pdm(["show"], obj=project)
    assert result.exit_code == 0, result.stderr

    result = pdm(["show", "--name", "--version"], obj=project)
    assert result.exit_code == 0
    assert "test-project\n0.0.0\n" == result.output


def test_export_to_requirements_txt(pdm, fixture_project):
    project = fixture_project("demo-package")
    requirements_txt = project.root / "requirements.txt"
    requirements_no_hashes = project.root / "requirements_simple.txt"
    requirements_pyproject = project.root / "requirements.ini"

    result = pdm(["export"], obj=project)
    assert result.exit_code == 0
    assert result.output.strip() == requirements_txt.read_text().strip()

    result = pdm(["export", "--self"], obj=project)
    assert result.exit_code == 1

    result = pdm(["export", "--editable-self"], obj=project)
    assert result.exit_code == 1

    result = pdm(["export", "--no-hashes", "--self"], obj=project)
    assert result.exit_code == 0
    assert ".  # this package\n" in result.output.strip()

    result = pdm(["export", "--no-hashes", "--editable-self"], obj=project)
    assert result.exit_code == 0
    assert "-e .  # this package\n" in result.output.strip()

    result = pdm(["export", "--no-hashes"], obj=project)
    assert result.exit_code == 0
    assert result.output.strip() == requirements_no_hashes.read_text().strip()

    result = pdm(["export", "--pyproject"], obj=project)
    assert result.exit_code == 0
    assert result.output.strip() == requirements_pyproject.read_text().strip()

    result = pdm(["export", "-o", str(project.root / "requirements_output.txt")], obj=project)
    assert result.exit_code == 0
    assert (project.root / "requirements_output.txt").read_text() == requirements_txt.read_text()


@pytest.mark.parametrize("extra_opt", [[], ["--no-extras"]])
def test_export_doesnt_include_dep_with_extras(pdm, fixture_project, extra_opt):
    project = fixture_project("demo-package-has-dep-with-extras")

    result = pdm(["export", "--without-hashes", *extra_opt], obj=project)
    assert result.exit_code == 0
    if extra_opt:
        assert "requests==2.26.0" in result.output.splitlines()
    else:
        assert "requests[security]==2.26.0" in result.output.splitlines()


def test_completion_command(pdm):
    result = pdm(["completion", "bash"])
    assert result.exit_code == 0
    assert "(completion)" in result.output


@pytest.mark.network
def test_show_update_hint(pdm, project, monkeypatch):
    monkeypatch.delenv("PDM_CHECK_UPDATE", raising=False)
    prev_version = project.core.version
    try:
        project.core.version = "0.0.0"
        r = pdm(["config"], obj=project)
    finally:
        project.core.version = prev_version
    assert "to upgrade." in r.stderr
    assert "Run `pdm config check_update false` to disable the check." in r.stderr


@pytest.mark.usefixtures("repository")
def test_export_with_platform_markers(pdm, project):
    pdm(["add", "--no-sync", 'urllib3; sys_platform == "fake"'], obj=project, strict=True)
    result = pdm(["export", "--no-hashes"], obj=project, strict=True)
    assert 'urllib3==1.22; sys_platform == "fake"' in result.output.splitlines()


@pytest.mark.usefixtures("repository", "vcs")
def test_export_with_vcs_deps(pdm, project):
    pdm(["add", "--no-sync", "git+https://github.com/test-root/demo.git"], obj=project, strict=True)
    result = pdm(["export"], obj=project)
    assert result.exit_code != 0

    result = pdm(["export", "--no-hashes"], obj=project)
    assert result.exit_code == 0
    assert "demo @ git+https://github.com/test-root/demo.git@1234567890abcdef" in result.output.splitlines()
