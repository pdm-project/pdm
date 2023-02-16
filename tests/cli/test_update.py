import pytest

from pdm.cli import actions
from pdm.exceptions import PdmUsageError


@pytest.mark.usefixtures("repository", "working_set")
def test_update_packages_with_top(project):
    actions.do_add(project, packages=("requests",))
    with pytest.raises(PdmUsageError):
        actions.do_update(project, packages=("requests",), top=True)


def test_update_command(project, invoke, mocker):
    do_update = mocker.patch.object(actions, "do_update")
    invoke(["update"], obj=project)
    do_update.assert_called_once()


@pytest.mark.usefixtures("working_set")
def test_update_ignore_constraints(project, repository):
    actions.do_add(project, packages=("pytz",))
    assert project.pyproject.metadata["dependencies"] == ["pytz~=2019.3"]
    repository.add_candidate("pytz", "2020.2")

    actions.do_update(project, unconstrained=False, packages=("pytz",))
    assert project.pyproject.metadata["dependencies"] == ["pytz~=2019.3"]
    assert project.locked_repository.all_candidates["pytz"].version == "2019.3"

    actions.do_update(project, unconstrained=True, packages=("pytz",))
    assert project.pyproject.metadata["dependencies"] == ["pytz~=2020.2"]
    assert project.locked_repository.all_candidates["pytz"].version == "2020.2"


@pytest.mark.usefixtures("working_set")
@pytest.mark.parametrize("strategy", ["reuse", "all"])
def test_update_all_packages(project, repository, capsys, strategy):
    actions.do_add(project, packages=["requests", "pytz"])
    repository.add_candidate("pytz", "2019.6")
    repository.add_candidate("chardet", "3.0.5")
    repository.add_candidate("requests", "2.20.0")
    repository.add_dependencies(
        "requests",
        "2.20.0",
        [
            "certifi>=2017.4.17",
            "chardet<3.1.0,>=3.0.2",
            "idna<2.8,>=2.5",
            "urllib3<1.24,>=1.21.1",
        ],
    )
    actions.do_update(project, strategy=strategy)
    locked_candidates = project.locked_repository.all_candidates
    assert locked_candidates["requests"].version == "2.20.0"
    assert locked_candidates["chardet"].version == ("3.0.5" if strategy == "all" else "3.0.4")
    assert locked_candidates["pytz"].version == "2019.6"
    out, _ = capsys.readouterr()
    update_num = 3 if strategy == "all" else 2
    assert f"{update_num} to update" in out, out

    actions.do_sync(project)
    out, _ = capsys.readouterr()
    assert "All packages are synced to date" in out


@pytest.mark.usefixtures("working_set")
def test_update_dry_run(project, repository, capsys):
    actions.do_add(project, packages=["requests", "pytz"])
    repository.add_candidate("pytz", "2019.6")
    repository.add_candidate("chardet", "3.0.5")
    repository.add_candidate("requests", "2.20.0")
    repository.add_dependencies(
        "requests",
        "2.20.0",
        [
            "certifi>=2017.4.17",
            "chardet<3.1.0,>=3.0.2",
            "idna<2.8,>=2.5",
            "urllib3<1.24,>=1.21.1",
        ],
    )
    actions.do_update(project, dry_run=True)
    out, _ = capsys.readouterr()
    project.lockfile.reload()
    locked_candidates = project.locked_repository.all_candidates
    assert locked_candidates["requests"].version == "2.19.1"
    assert locked_candidates["chardet"].version == "3.0.4"
    assert locked_candidates["pytz"].version == "2019.3"
    assert "requests 2.19.1 -> 2.20.0" in out


@pytest.mark.usefixtures("working_set")
def test_update_top_packages_dry_run(project, repository, capsys):
    actions.do_add(project, packages=["requests", "pytz"])
    repository.add_candidate("pytz", "2019.6")
    repository.add_candidate("chardet", "3.0.5")
    repository.add_candidate("requests", "2.20.0")
    repository.add_dependencies(
        "requests",
        "2.20.0",
        [
            "certifi>=2017.4.17",
            "chardet<3.1.0,>=3.0.2",
            "idna<2.8,>=2.5",
            "urllib3<1.24,>=1.21.1",
        ],
    )
    actions.do_update(project, top=True, dry_run=True)
    out, _ = capsys.readouterr()
    assert "requests 2.19.1 -> 2.20.0" in out
    assert "- chardet 3.0.4 -> 3.0.5" not in out


@pytest.mark.usefixtures("working_set")
def test_update_specified_packages(project, repository):
    actions.do_add(project, sync=False, packages=["requests", "pytz"])
    repository.add_candidate("pytz", "2019.6")
    repository.add_candidate("chardet", "3.0.5")
    repository.add_candidate("requests", "2.20.0")
    repository.add_dependencies(
        "requests",
        "2.20.0",
        [
            "certifi>=2017.4.17",
            "chardet<3.1.0,>=3.0.2",
            "idna<2.8,>=2.5",
            "urllib3<1.24,>=1.21.1",
        ],
    )
    actions.do_update(project, packages=["requests"])
    locked_candidates = project.locked_repository.all_candidates
    assert locked_candidates["requests"].version == "2.20.0"
    assert locked_candidates["chardet"].version == "3.0.4"


@pytest.mark.usefixtures("working_set")
def test_update_specified_packages_eager_mode(project, repository):
    actions.do_add(project, sync=False, packages=["requests", "pytz"])
    repository.add_candidate("pytz", "2019.6")
    repository.add_candidate("chardet", "3.0.5")
    repository.add_candidate("requests", "2.20.0")
    repository.add_dependencies(
        "requests",
        "2.20.0",
        [
            "certifi>=2017.4.17",
            "chardet<3.1.0,>=3.0.2",
            "idna<2.8,>=2.5",
            "urllib3<1.24,>=1.21.1",
        ],
    )
    actions.do_update(project, strategy="eager", packages=["requests"])
    locked_candidates = project.locked_repository.all_candidates
    assert locked_candidates["requests"].version == "2.20.0"
    assert locked_candidates["chardet"].version == "3.0.5"
    assert locked_candidates["pytz"].version == "2019.3"


@pytest.mark.usefixtures("repository", "working_set")
def test_update_with_package_and_groups_argument(project):
    actions.do_add(project, packages=["requests", "pytz"])
    with pytest.raises(PdmUsageError):
        actions.do_update(project, groups=("default", "dev"), packages=("requests",))

    with pytest.raises(PdmUsageError):
        actions.do_update(project, default=False, packages=("requests",))


@pytest.mark.usefixtures("repository", "working_set")
def test_update_with_prerelease_without_package_argument(project):
    actions.do_add(project, packages=["requests"])
    with pytest.raises(PdmUsageError, match="--prerelease must be used with packages given"):
        actions.do_update(project, prerelease=True)


@pytest.mark.usefixtures("repository")
def test_update_existing_package_with_prerelease(project, working_set):
    actions.do_add(project, packages=["urllib3"])
    assert project.pyproject.metadata["dependencies"][0] == "urllib3~=1.22"
    assert working_set["urllib3"].version == "1.22"

    actions.do_update(project, packages=["urllib3"], prerelease=True)
    assert project.pyproject.metadata["dependencies"][0] == "urllib3~=1.22"
    assert working_set["urllib3"].version == "1.23b0"

    actions.do_update(project, packages=["urllib3"], prerelease=True, unconstrained=True)
    assert project.pyproject.metadata["dependencies"][0] == "urllib3<2,>=1.23b0"
    assert working_set["urllib3"].version == "1.23b0"


def test_update_package_with_extras(project, repository, working_set):
    repository.add_candidate("foo", "0.1")
    foo_deps = ["urllib3; extra == 'req'"]
    repository.add_dependencies("foo", "0.1", foo_deps)
    actions.do_add(project, packages=["foo[req]"])
    assert working_set["foo"].version == "0.1"

    repository.add_candidate("foo", "0.2")
    repository.add_dependencies("foo", "0.2", foo_deps)
    actions.do_update(project)
    assert working_set["foo"].version == "0.2"
    assert project.locked_repository.all_candidates["foo"].version == "0.2"
