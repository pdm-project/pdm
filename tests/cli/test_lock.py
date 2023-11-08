import sys
from unittest.mock import ANY

import pytest
from packaging.version import Version
from unearth import Link

from pdm.cli import actions
from pdm.exceptions import PdmUsageError
from pdm.models.requirements import parse_requirement
from pdm.models.specifiers import PySpecSet
from pdm.project.lockfile import FLAG_CROSS_PLATFORM, Compatibility


def test_lock_command(project, pdm, mocker):
    m = mocker.patch.object(actions, "do_lock")
    pdm(["lock"], obj=project)
    m.assert_called_with(project, refresh=False, groups=["default"], hooks=ANY, strategy_change=None)


@pytest.mark.usefixtures("repository")
def test_lock_dependencies(project):
    project.add_dependencies({"requests": parse_requirement("requests")})
    actions.do_lock(project)
    assert project.lockfile.exists
    locked = project.locked_repository.all_candidates
    for package in ("requests", "idna", "chardet", "certifi"):
        assert package in locked


@pytest.mark.parametrize("args", [("-S", "static_urls"), ("--static-urls",)])
def test_lock_refresh(pdm, project, repository, args):
    project.add_dependencies({"requests": parse_requirement("requests")})
    result = pdm(["lock"], obj=project)
    assert result.exit_code == 0
    assert project.is_lockfile_hash_match()
    package = next(p for p in project.lockfile["package"] if p["name"] == "requests")
    assert not package.get("files")
    project.add_dependencies({"requests": parse_requirement("requests>=2.0")})
    url_hashes = {
        "http://example.com/requests-2.19.1-py3-none-any.whl": "sha256:abcdef123456",
        "http://example2.com/requests-2.19.1-py3-none-AMD64.whl": "sha256:abcdef123456",
        "http://example1.com/requests-2.19.1-py3-none-any.whl": "sha256:abcdef123456",
    }
    repository.get_hashes = (
        lambda c: [{"url": url, "file": Link(url).filename, "hash": hash} for url, hash in url_hashes.items()]
        if c.identify() == "requests"
        else []
    )
    assert not project.is_lockfile_hash_match()
    result = pdm(["lock", "--refresh", "-v"], obj=project)
    assert result.exit_code == 0
    package = next(p for p in project.lockfile["package"] if p["name"] == "requests")
    assert package["files"] == [
        {"file": "requests-2.19.1-py3-none-AMD64.whl", "hash": "sha256:abcdef123456"},
        {"file": "requests-2.19.1-py3-none-any.whl", "hash": "sha256:abcdef123456"},
    ]
    assert project.is_lockfile_hash_match()
    result = pdm(["lock", "--refresh", *args, "-v"], obj=project)
    assert result.exit_code == 0
    package = next(p for p in project.lockfile["package"] if p["name"] == "requests")
    assert package["files"] == [{"url": url, "hash": hash} for url, hash in sorted(url_hashes.items())]


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
    assert FLAG_CROSS_PLATFORM in project.lockfile.strategy
    package = next(p for p in project.lockfile["package"] if p["name"] == "pdm-hello")
    file_hashes = package["files"]
    assert len(file_hashes) == 2


@pytest.mark.usefixtures("local_finder")
@pytest.mark.parametrize("args", [("--no-cross-platform",), ("-S", "no_cross_platform")])
def test_lock_current_platform_wheels(project, pdm, args):
    project.environment.python_requires = PySpecSet(">=3.7")
    project.add_dependencies({"pdm-hello": parse_requirement("pdm-hello")})
    pdm(["lock", *args], obj=project, strict=True)
    assert FLAG_CROSS_PLATFORM not in project.lockfile.strategy
    package = next(p for p in project.lockfile["package"] if p["name"] == "pdm-hello")
    file_hashes = package["files"]
    wheels_num = 2 if sys.platform == "win32" and not project.python.is_32bit else 1
    assert len(file_hashes) == wheels_num


def test_parse_lock_strategy_group_options(core):
    core.init_parser()
    parser = core.parser

    ns = parser.parse_args(["lock", "-S", "no_cross_platform"])
    assert ns.strategy_change == ["no_cross_platform"]
    ns = parser.parse_args(["lock", "-S", "no_cross_platform", "--static-urls"])
    assert ns.strategy_change == ["no_cross_platform", "static_urls"]
    ns = parser.parse_args(["lock", "-S", "no_cross_platform,direct_minimal_versions"])
    assert ns.strategy_change == ["no_cross_platform", "direct_minimal_versions"]


def test_apply_lock_strategy_changes(project):
    assert project.lockfile.apply_strategy_change(["no_cross_platform", "static_urls"]) == {"static_urls"}
    assert project.lockfile.apply_strategy_change(["no_static_urls"]) == {"cross_platform"}
    assert project.lockfile.apply_strategy_change([]) == {"cross_platform"}
    assert project.lockfile.apply_strategy_change(["no-cross-platform"]) == set()


@pytest.mark.parametrize("strategy", [["abc"], ["no_abc", "static_urls"]])
def test_apply_lock_strategy_changes_invalid(project, strategy):
    with pytest.raises(PdmUsageError):
        project.lockfile.apply_strategy_change(strategy)


def test_lock_direct_minimal_versions(project, repository, pdm):
    project.add_dependencies({"django": parse_requirement("django")})
    repository.add_candidate("pytz", "2019.6")
    pdm(["lock", "-S", "direct_minimal_versions"], obj=project, strict=True)
    assert project.lockfile.strategy == {"direct_minimal_versions", "cross_platform"}
    locked_repository = project.locked_repository
    assert locked_repository.all_candidates["django"].version == "1.11.8"
    assert locked_repository.all_candidates["pytz"].version == "2019.6"


@pytest.mark.usefixtures("local_finder")
@pytest.mark.parametrize("args", [(), ("-S", "direct_minimal_versions")])
def test_lock_direct_minimal_versions_real(project, pdm, args):
    project.add_dependencies({"zipp": parse_requirement("zipp")})
    pdm(["lock", *args], obj=project, strict=True)
    locked_candidate = project.locked_repository.all_candidates["zipp"]
    if args:
        assert locked_candidate.version == "3.6.0"
    else:
        assert locked_candidate.version == "3.7.0"


@pytest.mark.parametrize(
    "lock_version,expected",
    [
        ("4.1.0", Compatibility.BACKWARD),
        ("4.1.1", Compatibility.SAME),
        ("4.1.2", Compatibility.FORWARD),
        ("4.2", Compatibility.NONE),
        ("3.0", Compatibility.NONE),
        ("4.0.1", Compatibility.BACKWARD),
    ],
)
def test_lockfile_compatibility(project, monkeypatch, lock_version, expected, pdm):
    pdm(["lock"], obj=project, strict=True)
    monkeypatch.setattr("pdm.project.lockfile.Lockfile.spec_version", Version("4.1.1"))
    project.lockfile._data["metadata"]["lock_version"] = lock_version
    assert project.lockfile.compatibility() == expected
    result = pdm(["lock", "--check"], obj=project)
    assert result.exit_code == (1 if expected == Compatibility.NONE else 0)
