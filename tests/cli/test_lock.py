import sys
from unittest.mock import ANY

import pytest
from unearth import Link

from pdm.cli import actions
from pdm.models.requirements import parse_requirement
from pdm.models.specifiers import PySpecSet


def test_lock_command(project, pdm, mocker):
    m = mocker.patch.object(actions, "do_lock")
    pdm(["lock"], obj=project)
    m.assert_called_with(project, refresh=False, groups=["default"], hooks=ANY)


@pytest.mark.usefixtures("repository")
def test_lock_dependencies(project):
    project.add_dependencies({"requests": parse_requirement("requests")})
    actions.do_lock(project)
    assert project.lockfile.exists
    locked = project.locked_repository.all_candidates
    for package in ("requests", "idna", "chardet", "certifi"):
        assert package in locked


def test_lock_refresh(pdm, project, repository):
    project.add_dependencies({"requests": parse_requirement("requests")})
    result = pdm(["lock"], obj=project)
    assert result.exit_code == 0
    assert project.is_lockfile_hash_match()
    assert not project.lockfile["metadata"]["files"].get("requests 2.19.1")
    project.add_dependencies({"requests": parse_requirement("requests>=2.0")})
    url_hashes = {
        "http://example.com/requests-2.19.1-py3-none-any.whl": "sha256:abcdef123456",
        "http://example2.com/requests-2.19.1-py3-none-AMD64.whl": "sha256:abcdef123456",
        "http://example1.com/requests-2.19.1-py3-none-any.whl": "sha256:abcdef123456",
    }
    repository.get_hashes = lambda c: (
        {Link(url): hash for url, hash in url_hashes.items()} if c.identify() == "requests" else {}
    )
    assert not project.is_lockfile_hash_match()
    result = pdm(["lock", "--refresh", "-v"], obj=project)
    assert result.exit_code == 0
    assert project.is_lockfile_hash_match()
    assert project.lockfile["metadata"]["files"]["requests 2.19.1"] == [
        {"url": url, "hash": hash} for url, hash in sorted(url_hashes.items())
    ]


def test_lock_refresh_keep_consistent(pdm, project, repository):
    project.add_dependencies({"requests": parse_requirement("requests")})
    result = pdm(["lock"], obj=project)
    assert result.exit_code == 0
    assert project.is_lockfile_hash_match()
    previous = project.lockfile._path.read_text()
    result = pdm(["lock", "--refresh"], obj=project)
    assert result.exit_code == 0
    assert project.lockfile._path.read_text() == previous


def test_lock_check_no_change_success(pdm, project, repository):
    project.add_dependencies({"requests": parse_requirement("requests")})
    result = pdm(["lock"], obj=project)
    assert result.exit_code == 0
    assert project.is_lockfile_hash_match()

    result = pdm(["lock", "--check"], obj=project)
    assert result.exit_code == 0


def test_lock_check_change_fails(pdm, project, repository):
    project.add_dependencies({"requests": parse_requirement("requests")})
    result = pdm(["lock"], obj=project)
    assert result.exit_code == 0
    assert project.is_lockfile_hash_match()

    project.add_dependencies({"pyyaml": parse_requirement("pyyaml")})
    result = pdm(["lock", "--check"], obj=project)
    assert result.exit_code == 1


@pytest.mark.usefixtures("repository")
def test_innovations_with_specified_lockfile(pdm, project, working_set):
    project.add_dependencies({"requests": parse_requirement("requests")})
    lockfile = str(project.root / "mylock.lock")
    pdm(["lock", "--lockfile", lockfile], strict=True, obj=project)
    assert project.lockfile._path == project.root / "mylock.lock"
    assert project.is_lockfile_hash_match()
    locked = project.locked_repository.all_candidates
    assert "requests" in locked
    pdm(["sync", "--lockfile", lockfile], strict=True, obj=project)
    assert "requests" in working_set


@pytest.mark.usefixtures("repository", "vcs")
def test_skip_editable_dependencies_in_metadata(project, capsys):
    project.pyproject.metadata["dependencies"] = [
        "-e git+https://github.com/test-root/demo.git@1234567890abcdef#egg=demo"
    ]
    actions.do_lock(project)
    _, err = capsys.readouterr()
    assert "WARNING: Skipping editable dependency" in err
    assert not project.locked_repository.all_candidates


@pytest.mark.usefixtures("repository")
def test_lock_selected_groups(project, pdm):
    project.add_dependencies({"requests": parse_requirement("requests")}, to_group="http")
    project.add_dependencies({"pytz": parse_requirement("pytz")})
    pdm(["lock", "-G", "http", "--no-default"], obj=project, strict=True)
    assert project.lockfile.groups == ["http"]
    assert "requests" in project.locked_repository.all_candidates
    assert "pytz" not in project.locked_repository.all_candidates


@pytest.mark.usefixtures("repository")
@pytest.mark.parametrize("to_dev", [False, True])
def test_lock_self_referencing_groups(project, pdm, to_dev):
    name = project.name
    project.add_dependencies({"requests": parse_requirement("requests")}, to_group="http", dev=to_dev)
    project.add_dependencies(
        {"pytz": parse_requirement("pytz"), f"{name}[http]": parse_requirement(f"{name}[http]")},
        to_group="dev",
        dev=True,
    )
    pdm(["lock", "-G", "dev"], obj=project, strict=True)
    assert project.lockfile.groups == ["default", "dev"]
    assert "requests" in project.locked_repository.all_candidates


@pytest.mark.usefixtures("local_finder")
def test_lock_multiple_platform_wheels(project, pdm):
    project.environment.python_requires = PySpecSet(">=3.7")
    project.add_dependencies({"pdm-hello": parse_requirement("pdm-hello")})
    pdm(["lock"], obj=project, strict=True)
    assert project.lockfile.cross_platform
    file_hashes = project.lockfile["metadata"]["files"]["pdm-hello 0.1.0"]
    assert len(file_hashes) == 2


@pytest.mark.usefixtures("local_finder")
def test_lock_current_platform_wheels(project, pdm):
    project.environment.python_requires = PySpecSet(">=3.7")
    project.add_dependencies({"pdm-hello": parse_requirement("pdm-hello")})
    pdm(["lock", "--no-cross-platform"], obj=project, strict=True)
    assert project.lockfile.cross_platform is False
    file_hashes = project.lockfile["metadata"]["files"]["pdm-hello 0.1.0"]
    wheels_num = 2 if sys.platform == "win32" else 1
    assert len(file_hashes) == wheels_num
