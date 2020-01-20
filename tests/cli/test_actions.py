import pytest

from pdm.cli.actions import do_add, do_update, do_sync, do_remove
from collections import namedtuple

from pdm.exceptions import PdmUsageError

Requirement = namedtuple("Requirement", "key")
Candidate = namedtuple("Candidate", "req,version")


def make_candidate(name, version):
    req = Requirement(name)
    return Candidate(req=req, version=version)


def test_sync_only_different(project, repository, synchronizer, capsys):
    synchronizer.install_candidates(
        [
            make_candidate("foo", "0.1.0"),
            make_candidate("chardet", "3.0.1"),
            make_candidate("idna", "2.7"),
        ]
    )
    do_add(project, packages=["requests"])
    out, _ = capsys.readouterr()
    assert "3 packages added" in out
    assert "1 package updated" in out
    assert "foo" in synchronizer.working_set
    assert synchronizer.working_set["chardet"] == "3.0.4"


def test_sync_clean_packages(project, repository, synchronizer):
    synchronizer.install_candidates(
        [
            make_candidate("foo", "0.1.0"),
            make_candidate("chardet", "3.0.1"),
            make_candidate("idna", "2.7"),
        ]
    )
    do_add(project, packages=["requests"], sync=False)
    do_sync(project, clean=True)
    assert "foo" not in synchronizer.working_set


def test_sync_dry_run(project, repository, synchronizer):
    synchronizer.install_candidates(
        [
            make_candidate("foo", "0.1.0"),
            make_candidate("chardet", "3.0.1"),
            make_candidate("idna", "2.7"),
        ]
    )
    do_add(project, packages=["requests"], sync=False)
    do_sync(project, clean=True, dry_run=True)
    assert "foo" in synchronizer.working_set
    assert "requests" not in synchronizer.working_set
    assert synchronizer.working_set["chardet"] == "3.0.1"


def test_add_package(project, repository, synchronizer, is_dev):
    do_add(project, is_dev, packages=["requests"])
    section = "dev-dependencies" if is_dev else "dependencies"

    assert project.tool_settings[section]["requests"] == "<3.0.0,>=2.19.1"
    locked_candidates = project.get_locked_candidates("dev" if is_dev else "default")
    assert locked_candidates["idna"].version == "2.7"
    for package in ("requests", "idna", "chardet", "urllib3", "certifi"):
        assert package in synchronizer.working_set


def test_add_package_to_custom_package(project, repository, synchronizer):
    do_add(project, section="test", packages=["requests"])

    assert "requests" in project.tool_settings["test-dependencies"]
    locked_candidates = project.get_locked_candidates("test")
    assert locked_candidates["idna"].version == "2.7"
    for package in ("requests", "idna", "chardet", "urllib3", "certifi"):
        assert package in synchronizer.working_set


def test_add_editable_package(project, repository, synchronizer, is_dev, vcs):
    do_add(
        project,
        is_dev,
        editables=["git+https://github.com/test-root/demo.git#egg=demo"],
    )
    section = "dev-dependencies" if is_dev else "dependencies"
    assert "demo" in project.tool_settings[section]
    locked_candidates = project.get_locked_candidates("dev" if is_dev else "default")
    assert locked_candidates["idna"].version == "2.7"
    assert "idna" in synchronizer.working_set


def test_add_no_install(project, repository, synchronizer):
    do_add(project, sync=False, packages=["requests"])
    for package in ("requests", "idna", "chardet", "urllib3", "certifi"):
        assert package not in synchronizer.working_set


def test_add_package_save_exact(project, repository):
    do_add(project, sync=False, save="exact", packages=["requests"])
    assert project.tool_settings["dependencies"]["requests"] == "==2.19.1"


def test_add_package_save_wildcard(project, repository):
    do_add(project, sync=False, save="wildcard", packages=["requests"])
    assert project.tool_settings["dependencies"]["requests"] == "*"


def test_add_package_update_reuse(project, repository):
    do_add(project, sync=False, save="wildcard", packages=["requests", "pytz"])

    locked_candidates = project.get_locked_candidates()
    assert locked_candidates["requests"].version == "2.19.1"
    assert locked_candidates["chardet"].version == "3.0.4"
    assert locked_candidates["pytz"].version == "2019.3"

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
    do_add(
        project, sync=False, save="wildcard", packages=["requests"], strategy="reuse"
    )
    locked_candidates = project.get_locked_candidates()
    assert locked_candidates["requests"].version == "2.20.0"
    assert locked_candidates["chardet"].version == "3.0.4"
    assert locked_candidates["pytz"].version == "2019.3"


def test_add_package_update_eager(project, repository):
    do_add(project, sync=False, save="wildcard", packages=["requests", "pytz"])

    locked_candidates = project.get_locked_candidates()
    assert locked_candidates["requests"].version == "2.19.1"
    assert locked_candidates["chardet"].version == "3.0.4"
    assert locked_candidates["pytz"].version == "2019.3"

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
    do_add(
        project, sync=False, save="wildcard", packages=["requests"], strategy="eager"
    )
    locked_candidates = project.get_locked_candidates()
    assert locked_candidates["requests"].version == "2.20.0"
    assert locked_candidates["chardet"].version == "3.0.5"
    assert locked_candidates["pytz"].version == "2019.3"


def test_update_all_packages(project, repository, synchronizer, capsys):
    do_add(project, packages=["requests", "pytz"])
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
    do_update(project)
    locked_candidates = project.get_locked_candidates()
    assert locked_candidates["requests"].version == "2.20.0"
    assert locked_candidates["chardet"].version == "3.0.5"
    assert locked_candidates["pytz"].version == "2019.6"
    out, _ = capsys.readouterr()
    assert "3 packages updated" in out

    do_sync(project)
    out, _ = capsys.readouterr()
    assert "All packages are synced to date" in out


def test_update_specified_packages(project, repository, synchronizer):
    do_add(project, sync=False, packages=["requests", "pytz"])
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
    do_update(project, packages=["requests"])
    locked_candidates = project.get_locked_candidates()
    assert locked_candidates["requests"].version == "2.20.0"
    assert locked_candidates["chardet"].version == "3.0.4"


def test_update_specified_packages_eager_mode(project, repository, synchronizer):
    do_add(project, sync=False, packages=["requests", "pytz"])
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
    do_update(project, strategy="eager", packages=["requests"])
    locked_candidates = project.get_locked_candidates()
    assert locked_candidates["requests"].version == "2.20.0"
    assert locked_candidates["chardet"].version == "3.0.5"
    assert locked_candidates["pytz"].version == "2019.3"


def test_remove_package(project, repository, synchronizer, is_dev):
    do_add(project, dev=is_dev, packages=["requests", "pytz"])
    do_remove(project, dev=is_dev, packages=["pytz"])
    locked_candidates = project.get_locked_candidates()
    assert "pytz" not in locked_candidates
    assert "pytz" not in synchronizer.working_set


def test_remove_package_no_sync(project, repository, synchronizer):
    do_add(project, packages=["requests", "pytz"])
    do_remove(project, sync=False, packages=["pytz"])
    locked_candidates = project.get_locked_candidates()
    assert "pytz" not in locked_candidates
    assert "pytz" in synchronizer.working_set


def test_remove_package_not_exist(project, repository, synchronizer):
    do_add(project, packages=["requests", "pytz"])
    with pytest.raises(PdmUsageError):
        do_remove(project, sync=False, packages=["django"])


def test_add_remove_no_package(project, repository):
    with pytest.raises(PdmUsageError):
        do_add(project, packages=())

    with pytest.raises(PdmUsageError):
        do_remove(project, packages=())


def test_update_with_package_and_sections_argument(project, repository, synchronizer):
    do_add(project, packages=["requests", "pytz"])
    with pytest.raises(PdmUsageError):
        do_update(project, sections=("default", "dev"), packages=("requests",))

    with pytest.raises(PdmUsageError):
        do_update(project, default=False, packages=("requests",))


def test_add_package_with_mismatch_marker(project, repository, synchronizer, mocker):
    mocker.patch(
        "pdm.models.environment.get_pep508_environment",
        return_value={"platform_system": "Darwin"},
    )
    do_add(project, packages=["requests", "pytz; platform_system!='Darwin'"])
    assert "pytz" not in synchronizer.working_set


def test_add_dependency_from_multiple_parents(
    project, repository, synchronizer, mocker
):
    mocker.patch(
        "pdm.models.environment.get_pep508_environment",
        return_value={"platform_system": "Darwin"},
    )
    do_add(project, packages=["requests", "chardet; platform_system!='Darwin'"])
    assert "chardet" in synchronizer.working_set
