import pytest

from pdm.cli import actions
from pdm.cli.commands.remove import Command
from pdm.cli.filters import GroupSelection
from pdm.models.specifiers import PySpecSet
from pdm.utils import cd


def make_workspace_member(project, core):
    project.pyproject.settings["workspace"] = {"members": ["packages/*"]}
    project.pyproject.write()
    member_path = project.root / "packages" / "foo"
    member_path.mkdir(parents=True)
    member_path.joinpath("pyproject.toml").write_text(
        '[project]\nname = "foo"\nversion = "0.1.0"\ndependencies = ["requests"]\n',
        encoding="utf-8",
    )
    return core.create_project(member_path, global_config=project.global_config.config_file.as_posix())


def test_remove_command(project, pdm, mocker):
    do_remove = mocker.patch("pdm.cli.commands.remove.Command.do_remove")
    pdm(["remove", "demo"], obj=project)
    do_remove.assert_called_once()


@pytest.mark.usefixtures("working_set", "vcs")
def test_remove_editable_packages_while_keeping_normal(project, pdm):
    project.environment.python_requires = PySpecSet(">=3.6")
    pdm(["add", "demo"], obj=project, strict=True)
    pdm(["add", "-d", "-e", "git+https://github.com/test-root/demo.git#egg=demo"], obj=project, strict=True)
    pdm(["remove", "-d", "demo"], obj=project, strict=True)
    default_group = project.pyproject.metadata["dependencies"]
    dev_group = project.pyproject.dev_dependencies.get("dev")
    assert not dev_group
    assert len(default_group) == 1
    assert not project.get_locked_repository().candidates["demo"].req.editable


def test_remove_package(project, working_set, dev_option, pdm):
    pdm(["add", *dev_option, "requests", "pytz"], obj=project, strict=True)
    pdm(["remove", *dev_option, "pytz"], obj=project, strict=True)
    locked_candidates = project.get_locked_repository().candidates
    assert "pytz" not in locked_candidates
    assert "pytz" not in working_set


def test_remove_package_no_lock(project, working_set, dev_option, pdm):
    pdm(["add", *dev_option, "requests", "pytz"], obj=project, strict=True)
    pdm(["remove", *dev_option, "--frozen-lockfile", "pytz"], obj=project, strict=True)
    assert "pytz" not in working_set
    project.lockfile.reload()
    locked_candidates = project.get_locked_repository().candidates
    assert "pytz" in locked_candidates


def test_remove_package_with_dry_run(project, working_set, pdm):
    pdm(["add", "requests"], obj=project, strict=True)
    result = pdm(["remove", "requests", "--dry-run"], obj=project, strict=True)
    project._lockfile = None
    locked_candidates = project.get_locked_repository().candidates
    assert "urllib3" in locked_candidates
    assert "urllib3" in working_set
    assert "- urllib3 1.22" in result.output


def test_remove_package_no_sync(project, working_set, pdm):
    pdm(["add", "requests", "pytz"], obj=project, strict=True)
    pdm(["remove", "pytz", "--no-sync"], obj=project, strict=True)
    locked_candidates = project.get_locked_repository().candidates
    assert "pytz" not in locked_candidates
    assert "pytz" in working_set


@pytest.mark.usefixtures("working_set")
def test_remove_package_not_exist(project, pdm):
    pdm(["add", "requests", "pytz"], obj=project, strict=True)
    result = pdm(["remove", "django"], obj=project)
    assert result.exit_code == 1


def test_remove_package_exist_in_multi_groups(project, working_set, pdm):
    pdm(["add", "requests"], obj=project, strict=True)
    pdm(["add", "--dev", "urllib3"], obj=project, strict=True)
    pdm(["remove", "--dev", "urllib3"], obj=project, strict=True)
    assert "dependency-groups" not in project.pyproject._data
    assert "urllib3" in working_set
    assert "requests" in working_set


@pytest.mark.usefixtures("repository")
def test_remove_no_package(project, pdm):
    result = pdm(["remove"], obj=project)
    assert result.exit_code != 0


@pytest.mark.usefixtures("working_set")
def test_remove_package_wont_break_toml(project_no_init, pdm):
    project_no_init.pyproject._path.write_text(
        """
[project]
dependencies = [
    "requests",
    # this is a comment
]
"""
    )
    project_no_init.pyproject.reload()
    pdm(["remove", "requests"], obj=project_no_init, strict=True)
    assert project_no_init.pyproject.metadata["dependencies"] == []


@pytest.mark.usefixtures("working_set")
def test_remove_group_not_in_lockfile(project, pdm, mocker):
    pdm(["add", "requests"], obj=project, strict=True)
    project.add_dependencies(["pytz"], to_group="tz")
    assert project.lockfile.groups == ["default"]
    locker = mocker.patch.object(actions, "do_lock")
    pdm(["remove", "--group", "tz", "pytz"], obj=project, strict=True)
    assert "optional-dependencies" not in project.pyproject.metadata
    locker.assert_not_called()


def test_remove_workspace_member_updates_root_lockfile(project, core, repository):
    member_project = make_workspace_member(project, core)
    actions.do_lock(member_project)
    assert "requests" in member_project.get_locked_repository().candidates

    Command.do_remove(
        member_project,
        selection=GroupSelection(member_project),
        packages=["requests"],
        sync=False,
    )

    assert (project.root / "pdm.lock").exists()
    assert not (member_project.root / "pdm.lock").exists()
    locked_candidates = member_project.get_locked_repository().candidates
    assert "foo" in locked_candidates
    assert "requests" not in locked_candidates


def test_remove_subdirectory_path_dependency_keeps_workspace_member(project, repository):
    member_path = project.root / "packages" / "foo"
    member_path.mkdir(parents=True)
    member_path.joinpath("pyproject.toml").write_text(
        '[project]\nname = "foo"\nversion = "0.1.0"\ndependencies = []\n',
        encoding="utf-8",
    )
    project.pyproject.settings["workspace"] = {"members": ["packages/foo"]}
    project.pyproject.metadata["dependencies"] = ["foo @ file:///${PROJECT_ROOT}/packages/foo"]
    project.pyproject.write()

    Command.do_remove(
        project,
        selection=GroupSelection(project),
        packages=["foo"],
        sync=False,
    )

    project.pyproject.reload()
    assert project.pyproject.settings["workspace"]["members"] == ["packages/foo"]
    assert project.pyproject.metadata["dependencies"] == []
    assert "foo" in project.get_locked_repository().candidates


def test_remove_workspace_member_not_in_dependencies(project, repository):
    member_path = project.root / "packages" / "foo"
    member_path.mkdir(parents=True)
    member_path.joinpath("pyproject.toml").write_text(
        '[project]\nname = "foo"\nversion = "0.1.0"\ndependencies = []\n',
        encoding="utf-8",
    )
    project.pyproject.settings["workspace"] = {"members": ["packages/foo"]}
    project.pyproject.write()

    with cd(project.root):
        Command.do_remove(
            project,
            selection=GroupSelection(project),
            packages=["packages/foo"],
            sync=False,
        )

    project.pyproject.reload()
    assert project.pyproject.settings["workspace"]["members"] == []
    assert project.pyproject.metadata["dependencies"] == []
    assert "foo" not in project.get_locked_repository().candidates


@pytest.mark.usefixtures("working_set")
def test_remove_exclude_non_existing_dev_group_in_lockfile(project, pdm):
    pdm(["add", "requests"], obj=project, strict=True)
    project.add_dependencies(["pytz"], to_group="tz", dev=True)
    assert project.lockfile.groups == ["default"]
    result = pdm(["remove", "requests"], obj=project)
    assert result.exit_code == 0


@pytest.mark.usefixtures("working_set")
def test_remove_package_with_group_include(project, pdm):
    project.pyproject._data["dependency-groups"] = {
        "web": ["requests"],
        "serve": [{"include-group": "web"}, "django"],
    }
    project.pyproject.write()
    pdm(["lock"], obj=project, strict=True)
    pdm(["remove", "--no-sync", "-Gserve", "django"], obj=project, strict=True)
    assert "django" not in project.pyproject.dependency_groups["serve"]
