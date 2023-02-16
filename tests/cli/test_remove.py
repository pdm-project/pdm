import pytest

from pdm.cli import actions
from pdm.exceptions import PdmException, PdmUsageError
from pdm.models.specifiers import PySpecSet


def test_remove_command(project, invoke, mocker):
    do_remove = mocker.patch.object(actions, "do_remove")
    invoke(["remove", "demo"], obj=project)
    do_remove.assert_called_once()


@pytest.mark.usefixtures("repository", "working_set", "vcs")
def test_remove_editable_packages_while_keeping_normal(project):
    project.environment.python_requires = PySpecSet(">=3.6")
    actions.do_add(project, packages=["demo"])
    actions.do_add(
        project,
        True,
        editables=["git+https://github.com/test-root/demo.git#egg=demo"],
    )
    dev_group = project.pyproject.settings["dev-dependencies"]["dev"]
    default_group = project.pyproject.metadata["dependencies"]
    actions.do_remove(project, True, packages=["demo"])
    assert not dev_group
    assert len(default_group) == 1
    assert not project.locked_repository.all_candidates["demo"].req.editable


@pytest.mark.usefixtures("repository")
def test_remove_package(project, working_set, is_dev):
    actions.do_add(project, dev=is_dev, packages=["requests", "pytz"])
    actions.do_remove(project, dev=is_dev, packages=["pytz"])
    locked_candidates = project.locked_repository.all_candidates
    assert "pytz" not in locked_candidates
    assert "pytz" not in working_set


@pytest.mark.usefixtures("repository")
def test_remove_package_with_dry_run(project, working_set, capsys):
    actions.do_add(project, packages=["requests"])
    actions.do_remove(project, packages=["requests"], dry_run=True)
    out, _ = capsys.readouterr()
    project._lockfile = None
    locked_candidates = project.locked_repository.all_candidates
    assert "urllib3" in locked_candidates
    assert "urllib3" in working_set
    assert "- urllib3 1.22" in out


@pytest.mark.usefixtures("repository")
def test_remove_package_no_sync(project, working_set):
    actions.do_add(project, packages=["requests", "pytz"])
    actions.do_remove(project, sync=False, packages=["pytz"])
    locked_candidates = project.locked_repository.all_candidates
    assert "pytz" not in locked_candidates
    assert "pytz" in working_set


@pytest.mark.usefixtures("repository", "working_set")
def test_remove_package_not_exist(project):
    actions.do_add(project, packages=["requests", "pytz"])
    with pytest.raises(PdmException):
        actions.do_remove(project, sync=False, packages=["django"])


@pytest.mark.usefixtures("repository")
def test_remove_package_exist_in_multi_groups(project, working_set):
    actions.do_add(project, packages=["requests"])
    actions.do_add(project, dev=True, packages=["urllib3"])
    actions.do_remove(project, dev=True, packages=["urllib3"])
    assert all("urllib3" not in line for line in project.pyproject.settings["dev-dependencies"]["dev"])
    assert "urllib3" in working_set
    assert "requests" in working_set


@pytest.mark.usefixtures("repository")
def test_add_remove_no_package(project):
    with pytest.raises(PdmUsageError):
        actions.do_add(project, packages=())

    with pytest.raises(PdmUsageError):
        actions.do_remove(project, packages=())


@pytest.mark.usefixtures("repository", "working_set")
def test_remove_package_wont_break_toml(project_no_init):
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
    actions.do_remove(project_no_init, packages=["requests"])
    assert project_no_init.pyproject.metadata["dependencies"] == []
