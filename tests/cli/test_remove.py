import pytest

from pdm.cli import actions
from pdm.exceptions import PdmException, PdmUsageError
from pdm.models.specifiers import PySpecSet


def test_remove_command(project, invoke, mocker):
    do_remove = mocker.patch.object(actions, "do_remove")
    invoke(["remove", "demo"], obj=project)
    do_remove.assert_called_once()


@pytest.mark.usefixtures("repository", "working_set", "vcs")
def test_remove_both_normal_and_editable_packages(project, is_dev):
    project.environment.python_requires = PySpecSet(">=3.6")
    actions.do_add(project, is_dev, packages=["demo"])
    actions.do_add(
        project,
        is_dev,
        editables=["git+https://github.com/test-root/demo.git#egg=demo"],
    )
    group = (
        project.tool_settings["dev-dependencies"]["dev"]
        if is_dev
        else project.meta["dependencies"]
    )
    actions.do_remove(project, is_dev, packages=["demo"])
    assert not group
    assert "demo" not in project.locked_repository.all_candidates


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
    assert all(
        "urllib3" not in line
        for line in project.tool_settings["dev-dependencies"]["dev"]
    )
    assert "urllib3" in working_set
    assert "requests" in working_set


@pytest.mark.usefixtures("repository")
def test_add_remove_no_package(project):
    with pytest.raises(PdmUsageError):
        actions.do_add(project, packages=())

    with pytest.raises(PdmUsageError):
        actions.do_remove(project, packages=())
