import pytest


@pytest.mark.usefixtures("working_set")
def test_update_packages_with_top(project, pdm):
    pdm(["add", "requests"], obj=project, strict=True)
    result = pdm(["update", "--top", "requests"], obj=project)
    assert "PdmUsageError" in result.stderr


def test_update_command(project, pdm, mocker):
    do_update = mocker.patch("pdm.cli.commands.update.Command.do_update")
    pdm(["update"], obj=project)
    do_update.assert_called_once()


@pytest.mark.usefixtures("working_set")
def test_update_ignore_constraints(project, repository, pdm):
    project.project_config["strategy.save"] = "compatible"
    pdm(["add", "pytz"], obj=project, strict=True)
    assert project.pyproject.metadata["dependencies"] == ["pytz~=2019.3"]
    repository.add_candidate("pytz", "2020.2")

    pdm(["update", "pytz"], obj=project, strict=True)
    assert project.pyproject.metadata["dependencies"] == ["pytz~=2019.3"]
    assert project.get_locked_repository().candidates["pytz"].version == "2019.3"

    pdm(["update", "pytz", "--unconstrained"], obj=project, strict=True)
    assert project.pyproject.metadata["dependencies"] == ["pytz~=2020.2"]
    assert project.get_locked_repository().candidates["pytz"].version == "2020.2"


@pytest.mark.usefixtures("working_set")
@pytest.mark.parametrize("strategy", ["reuse", "all"])
def test_update_all_packages(project, repository, pdm, strategy):
    pdm(["add", "requests", "pytz"], obj=project, strict=True)
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
    result = pdm(["update", f"--update-{strategy}"], obj=project, strict=True)
    locked_candidates = project.get_locked_repository().candidates
    assert locked_candidates["requests"].version == "2.20.0"
    assert locked_candidates["chardet"].version == ("3.0.5" if strategy == "all" else "3.0.4")
    assert locked_candidates["pytz"].version == "2019.6"
    update_num = 3 if strategy == "all" else 2
    assert f"{update_num} to update" in result.stdout, result.stdout

    result = pdm(["sync"], obj=project, strict=True)
    assert "All packages are synced to date" in result.stdout


def test_update_no_lock(project, working_set, repository, pdm):
    pdm(["add", "pytz"], obj=project, strict=True)
    repository.add_candidate("pytz", "2019.6")
    pdm(["update", "--frozen-lockfile"], obj=project, strict=True)
    assert working_set["pytz"].version == "2019.6"
    project.lockfile.reload()
    assert project.get_locked_repository().candidates["pytz"].version == "2019.3"


@pytest.mark.usefixtures("working_set")
def test_update_dry_run(project, repository, pdm):
    pdm(["add", "requests", "pytz"], obj=project, strict=True)
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
    result = pdm(["update", "--dry-run"], obj=project, strict=True)
    project.lockfile.reload()
    locked_candidates = project.get_locked_repository().candidates
    assert locked_candidates["requests"].version == "2.19.1"
    assert locked_candidates["chardet"].version == "3.0.4"
    assert locked_candidates["pytz"].version == "2019.3"
    assert "requests 2.19.1 -> 2.20.0" in result.stdout


@pytest.mark.usefixtures("working_set")
def test_update_top_packages_dry_run(project, repository, pdm):
    pdm(["add", "requests", "pytz"], obj=project, strict=True)
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
    result = pdm(["update", "--dry-run", "--top"], obj=project, strict=True)
    assert "requests 2.19.1 -> 2.20.0" in result.stdout
    assert "- chardet 3.0.4 -> 3.0.5" not in result.stdout


@pytest.mark.usefixtures("working_set")
def test_update_specified_packages(project, repository, pdm):
    pdm(["add", "requests", "pytz", "--no-sync"], obj=project, strict=True)
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
    pdm(["update", "requests"], obj=project, strict=True)
    locked_candidates = project.get_locked_repository().candidates
    assert locked_candidates["requests"].version == "2.20.0"
    assert locked_candidates["chardet"].version == "3.0.4"


@pytest.mark.usefixtures("working_set")
def test_update_specified_packages_eager_mode(project, repository, pdm):
    pdm(["add", "requests", "pytz", "--no-sync"], obj=project, strict=True)
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
    pdm(["update", "requests", "--update-eager"], obj=project, strict=True)
    locked_candidates = project.get_locked_repository().candidates
    assert locked_candidates["requests"].version == "2.20.0"
    assert locked_candidates["chardet"].version == "3.0.5"
    assert locked_candidates["pytz"].version == "2019.3"


@pytest.mark.usefixtures("working_set")
def test_update_transitive(project, repository, pdm):
    pdm(["add", "requests", "--no-sync"], obj=project, strict=True)
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
    pdm(["update", "chardet"], obj=project, strict=True)
    locked_candidates = project.get_locked_repository().candidates
    assert not any("chardet" in dependency for dependency in project.pyproject.metadata["dependencies"])
    assert locked_candidates["chardet"].version == "3.0.5"
    assert locked_candidates["requests"].version == "2.19.1"


@pytest.mark.usefixtures("working_set")
def test_update_transitive_nonexistant_dependencies(project, pdm):
    pdm(["add", "requests", "--no-sync"], obj=project, strict=True)
    result = pdm(["update", "numpy"], obj=project)
    assert "ProjectError" in result.stderr
    assert "numpy does not exist in" in result.stderr


@pytest.mark.usefixtures("working_set")
def test_update_package_wrong_group(project, pdm):
    pdm(["add", "-d", "requests"], obj=project, strict=True)
    result = pdm(["update", "requests"], obj=project)
    assert "ProjectError" in result.stderr
    assert "requests does not exist in default, but exists in dev" in result.stderr


@pytest.mark.usefixtures("working_set")
def test_update_transitive_non_transitive_dependencies(project, repository, pdm):
    pdm(["add", "requests", "pytz", "--no-sync"], obj=project, strict=True)
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
    pdm(["update", "requests", "chardet", "pytz"], obj=project, strict=True)
    locked_candidates = project.get_locked_repository().candidates
    assert not any("chardet" in dependency for dependency in project.pyproject.metadata["dependencies"])
    assert locked_candidates["requests"].version == "2.20.0"
    assert locked_candidates["chardet"].version == "3.0.5"
    assert locked_candidates["pytz"].version == "2019.6"


@pytest.mark.usefixtures("working_set")
def test_update_specified_packages_eager_mode_config(project, repository, pdm):
    pdm(["add", "requests", "pytz", "--no-sync"], obj=project, strict=True)
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
    pdm(["config", "strategy.update", "eager"], obj=project, strict=True)
    pdm(["update", "requests"], obj=project, strict=True)
    locked_candidates = project.get_locked_repository().candidates
    assert locked_candidates["requests"].version == "2.20.0"
    assert locked_candidates["chardet"].version == "3.0.5"
    assert locked_candidates["pytz"].version == "2019.3"


@pytest.mark.usefixtures("working_set")
def test_update_with_package_and_groups_argument(project, pdm):
    pdm(["add", "-G", "web", "requests"], obj=project, strict=True)
    pdm(["add", "-Gextra", "pytz"], obj=project, strict=True)
    result = pdm(["update", "requests", "--group", "web", "-G", "extra"], obj=project)
    assert "PdmUsageError" in result.stderr

    result = pdm(["update", "requests", "--no-default"], obj=project)
    assert "PdmUsageError" in result.stderr


@pytest.mark.usefixtures("working_set")
def test_update_with_prerelease_without_package_argument(project, pdm):
    pdm(["add", "requests"], obj=project, strict=True)
    result = pdm(["update", "--prerelease"], obj=project)
    assert "--prerelease/--stable must be used with packages given" in result.stderr


def test_update_existing_package_with_prerelease(project, working_set, pdm):
    project.project_config["strategy.save"] = "compatible"
    pdm(["add", "urllib3"], obj=project, strict=True)
    assert project.pyproject.metadata["dependencies"][0] == "urllib3~=1.22"
    assert working_set["urllib3"].version == "1.22"

    pdm(["update", "urllib3", "--prerelease"], obj=project, strict=True)
    assert project.pyproject.metadata["dependencies"][0] == "urllib3~=1.22"
    assert working_set["urllib3"].version == "1.23b0"

    pdm(["update", "urllib3"], obj=project, strict=True)  # prereleases should be kept
    assert working_set["urllib3"].version == "1.23b0"

    pdm(["update", "urllib3", "--stable"], obj=project, strict=True)
    assert working_set["urllib3"].version == "1.22"

    pdm(["update", "urllib3", "--prerelease", "--unconstrained"], obj=project, strict=True)
    assert project.pyproject.metadata["dependencies"][0] == "urllib3<2,>=1.23b0"
    assert working_set["urllib3"].version == "1.23b0"


def test_update_package_with_extras(project, repository, working_set, pdm):
    repository.add_candidate("foo", "0.1")
    foo_deps = ["urllib3; extra == 'req'"]
    repository.add_dependencies("foo", "0.1", foo_deps)
    pdm(["add", "foo[req]"], obj=project, strict=True)
    assert working_set["foo"].version == "0.1"

    repository.add_candidate("foo", "0.2")
    repository.add_dependencies("foo", "0.2", foo_deps)
    pdm(["update"], obj=project, strict=True)
    assert working_set["foo"].version == "0.2"
    assert project.get_locked_repository().candidates["foo"].version == "0.2"


def test_update_groups_in_lockfile(project, working_set, pdm, repository):
    pdm(["add", "requests"], obj=project, strict=True)
    repository.add_candidate("foo", "0.1")
    pdm(["add", "foo", "--group", "extra"], obj=project, strict=True)
    assert project.lockfile.groups == ["default", "extra"]
    repository.add_candidate("foo", "0.2")
    pdm(["update"], obj=project, strict=True)
    assert project.get_locked_repository().candidates["foo"].version == "0.2"
    assert working_set["foo"].version == "0.2"


def test_update_group_not_in_lockfile(project, working_set, pdm):
    pdm(["add", "requests"], obj=project, strict=True)
    project.add_dependencies(["pytz"], to_group="extra")
    result = pdm(["update", "--group", "extra"], obj=project)
    assert result.exit_code != 0
    assert "Requested groups not in lockfile: extra" in result.stderr
