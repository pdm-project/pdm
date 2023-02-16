from unittest.mock import ANY

import pytest
from unearth import Link

from pdm.cli import actions
from pdm.models.requirements import parse_requirement


def test_lock_command(project, invoke, mocker):
    m = mocker.patch.object(actions, "do_lock")
    invoke(["lock"], obj=project)
    m.assert_called_with(project, refresh=False, hooks=ANY)


@pytest.mark.usefixtures("repository")
def test_lock_dependencies(project):
    project.add_dependencies({"requests": parse_requirement("requests")})
    actions.do_lock(project)
    assert project.lockfile.exists
    locked = project.locked_repository.all_candidates
    for package in ("requests", "idna", "chardet", "certifi"):
        assert package in locked


def test_lock_refresh(invoke, project, repository):
    project.add_dependencies({"requests": parse_requirement("requests")})
    result = invoke(["lock"], obj=project)
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
    result = invoke(["lock", "--refresh", "-v"], obj=project)
    assert result.exit_code == 0
    assert project.is_lockfile_hash_match()
    assert project.lockfile["metadata"]["files"]["requests 2.19.1"] == [
        {"url": url, "hash": hash} for url, hash in sorted(url_hashes.items())
    ]


def test_lock_refresh_keep_consistent(invoke, project, repository):
    project.add_dependencies({"requests": parse_requirement("requests")})
    result = invoke(["lock"], obj=project)
    assert result.exit_code == 0
    assert project.is_lockfile_hash_match()
    previous = project.lockfile._path.read_text()
    result = invoke(["lock", "--refresh"], obj=project)
    assert result.exit_code == 0
    assert project.lockfile._path.read_text() == previous


def test_lock_check_no_change_success(invoke, project, repository):
    project.add_dependencies({"requests": parse_requirement("requests")})
    result = invoke(["lock"], obj=project)
    assert result.exit_code == 0
    assert project.is_lockfile_hash_match()

    result = invoke(["lock", "--check"], obj=project)
    assert result.exit_code == 0


def test_lock_check_change_fails(invoke, project, repository):
    project.add_dependencies({"requests": parse_requirement("requests")})
    result = invoke(["lock"], obj=project)
    assert result.exit_code == 0
    assert project.is_lockfile_hash_match()

    project.add_dependencies({"pyyaml": parse_requirement("pyyaml")})
    result = invoke(["lock", "--check"], obj=project)
    assert result.exit_code == 1


@pytest.mark.usefixtures("repository")
def test_innovations_with_specified_lockfile(invoke, project, working_set):
    project.add_dependencies({"requests": parse_requirement("requests")})
    lockfile = str(project.root / "mylock.lock")
    invoke(["lock", "--lockfile", lockfile], strict=True, obj=project)
    assert project.lockfile._path == project.root / "mylock.lock"
    assert project.is_lockfile_hash_match()
    locked = project.locked_repository.all_candidates
    assert "requests" in locked
    invoke(["sync", "--lockfile", lockfile], strict=True, obj=project)
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
