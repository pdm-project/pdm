import pytest

from pdm.cli import actions
from pdm.models.specifiers import PySpecSet


def test_remove_command(project, pdm, mocker):
    do_remove = mocker.patch("pdm.cli.commands.remove.Command.do_remove")
    pdm(["remove", "demo"], obj=project)
    do_remove.assert_called_once()


@pytest.mark.usefixtures("working_set", "vcs")
def test_remove_editable_packages_while_keeping_normal(project, pdm):
    project.environment.python_requires = PySpecSet(">=3.6")
    pdm(["add", "demo"], obj=project, strict=True)
    pdm(["add", "-d", "-e", "git+https://github.com/test-root/demo.git#egg=demo"], obj=project, strict=True)
    dev_group = project.pyproject.settings["dev-dependencies"]["dev"]
    default_group = project.pyproject.metadata["dependencies"]
    pdm(["remove", "-d", "demo"], obj=project, strict=True)
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
    assert "dev-dependencies" not in project.pyproject.settings
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
