from unittest.mock import ANY

import pytest
from unearth import Link

from pdm.cli import actions
from pdm.exceptions import PdmUsageError
from pdm.models.requirements import parse_requirement
from pdm.models.specifiers import PySpecSet
from pdm.project.lockfile import FLAG_CROSS_PLATFORM, Compatibility
from pdm.utils import parse_version, path_to_url
from tests import FIXTURES


def test_lock_command(project, pdm, mocker):
    m = mocker.patch.object(actions, "do_lock")
    pdm(["lock"], obj=project)
    m.assert_called_with(
        project,
        refresh=False,
        groups=["default"],
        hooks=ANY,
        strategy_change=None,
        strategy="all",
        append=False,
        env_spec=None,
    )


@pytest.mark.usefixtures("repository")
def test_lock_dependencies(project):
    project.add_dependencies(["requests"])
    actions.do_lock(project)
    assert project.lockfile.exists
    locked = project.get_locked_repository().candidates
    for package in ("requests", "idna", "chardet", "certifi"):
        assert package in locked


@pytest.mark.parametrize("args", [("-S", "static_urls"), ("--static-urls",)])
def test_lock_refresh(pdm, project, repository, args, core, mocker):
    project.add_dependencies(["requests"])
    result = pdm(["lock"], obj=project)
    assert result.exit_code == 0
    assert project.is_lockfile_hash_match()
    package = next(p for p in project.lockfile["package"] if p["name"] == "requests")
    assert not package.get("files")
    project.add_dependencies(["requests>=2.0"])
    url_hashes = {
        "http://example.com/requests-2.19.1-py3-none-any.whl": "sha256:abcdef123456",
        "http://example2.com/requests-2.19.1-py3-none-AMD64.whl": "sha256:abcdef123456",
        "http://example1.com/requests-2.19.1-py3-none-any.whl": "sha256:abcdef123456",
    }
    mocker.patch.object(
        core.repository_class,
        "get_hashes",
        side_effect=(
            lambda c: [{"url": url, "file": Link(url).filename, "hash": hash} for url, hash in url_hashes.items()]
            if c.identify() == "requests"
            else []
        ),
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
    project.add_dependencies(["requests"])
    result = pdm(["lock"], obj=project)
    assert result.exit_code == 0
    assert project.is_lockfile_hash_match()
    previous = project.lockfile._path.read_text()
    result = pdm(["lock", "--refresh"], obj=project)
    assert result.exit_code == 0
    assert project.lockfile._path.read_text() == previous


def test_lock_check_no_change_success(pdm, project, repository):
    project.add_dependencies(["requests"])
    result = pdm(["lock"], obj=project)
    assert result.exit_code == 0
    assert project.is_lockfile_hash_match()

    result = pdm(["lock", "--check"], obj=project)
    assert result.exit_code == 0


def test_lock_check_change_fails(pdm, project, repository):
    project.add_dependencies(["requests"])
    result = pdm(["lock"], obj=project)
    assert result.exit_code == 0
    assert project.is_lockfile_hash_match()

    project.add_dependencies(["pyyaml"])
    result = pdm(["lock", "--check"], obj=project)
    assert result.exit_code == 1


@pytest.mark.usefixtures("repository")
def test_innovations_with_specified_lockfile(pdm, project, working_set):
    project.add_dependencies(["requests"])
    lockfile = str(project.root / "mylock.lock")
    pdm(["lock", "--lockfile", lockfile], strict=True, obj=project)
    assert project.lockfile._path == project.root / "mylock.lock"
    assert project.is_lockfile_hash_match()
    locked = project.get_locked_repository().candidates
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
    assert not project.get_locked_repository().candidates


@pytest.mark.usefixtures("repository")
def test_lock_selected_groups(project, pdm):
    project.add_dependencies(["requests"], to_group="http")
    project.add_dependencies(["pytz"])
    pdm(["lock", "-G", "http", "--no-default"], obj=project, strict=True)
    assert project.lockfile.groups == ["http"]
    assert "requests" in project.get_locked_repository().candidates
    assert "pytz" not in project.get_locked_repository().candidates


@pytest.mark.usefixtures("repository")
@pytest.mark.parametrize("to_dev", [False, True])
def test_lock_self_referencing_groups(project, pdm, to_dev):
    name = project.name
    project.add_dependencies(["requests"], to_group="http", dev=to_dev)
    project.add_dependencies(
        {"pytz": parse_requirement("pytz"), f"{name}[http]": parse_requirement(f"{name}[http]")},
        to_group="dev",
        dev=True,
    )
    pdm(["lock", "-G", "dev"], obj=project, strict=True)
    assert project.lockfile.groups == ["default", "dev", "http"]
    packages = project.lockfile["package"]
    pytz = next(p for p in packages if p["name"] == "pytz")
    assert pytz["groups"] == ["dev"]
    requests = next(p for p in packages if p["name"] == "requests")
    assert requests["groups"] == ["dev", "http"]
    idna = next(p for p in packages if p["name"] == "idna")
    assert idna["groups"] == ["dev", "http"]


@pytest.mark.usefixtures("local_finder")
def test_lock_multiple_platform_wheels(project, pdm):
    project.environment.python_requires = PySpecSet(">=3.7")
    project.add_dependencies(["pdm-hello"])
    pdm(["lock"], obj=project, strict=True)
    package = next(p for p in project.lockfile["package"] if p["name"] == "pdm-hello")
    file_hashes = package["files"]
    assert len(file_hashes) == 2


@pytest.mark.usefixtures("local_finder")
@pytest.mark.parametrize("platform", ["linux", "macos", "windows"])
def test_lock_specific_platform_wheels(project, pdm, platform):
    project.environment.python_requires = PySpecSet(">=3.7")
    project.add_dependencies(["pdm-hello"])
    pdm(["lock", "--platform", platform], obj=project, strict=True)
    assert FLAG_CROSS_PLATFORM not in project.lockfile.strategy
    package = next(p for p in project.lockfile["package"] if p["name"] == "pdm-hello")
    file_hashes = package["files"]
    wheels_num = 2 if platform == "windows" else 1
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
    assert project.lockfile.apply_strategy_change(["no_cross_platform", "static_urls"]) == {
        "inherit_metadata",
        "static_urls",
    }
    assert project.lockfile.apply_strategy_change(["no_static_urls"]) == {"inherit_metadata"}
    assert project.lockfile.apply_strategy_change(["no_inherit_metadata"]) == set()


@pytest.mark.parametrize("strategy", [["abc"], ["no_abc", "static_urls"]])
def test_apply_lock_strategy_changes_invalid(project, strategy):
    with pytest.raises(PdmUsageError):
        project.lockfile.apply_strategy_change(strategy)


def test_lock_direct_minimal_versions(project, repository, pdm):
    project.add_dependencies(["django"])
    repository.add_candidate("pytz", "2019.6")
    pdm(["lock", "-S", "direct_minimal_versions"], obj=project, strict=True)
    assert project.lockfile.strategy == {"direct_minimal_versions", "inherit_metadata"}
    locked_repository = project.get_locked_repository()
    assert locked_repository.candidates["django"].version == "1.11.8"
    assert locked_repository.candidates["pytz"].version == "2019.6"


@pytest.mark.usefixtures("local_finder")
@pytest.mark.parametrize("args", [(), ("-S", "direct_minimal_versions")])
def test_lock_direct_minimal_versions_real(project, pdm, args):
    project.add_dependencies(["zipp"])
    pdm(["lock", *args], obj=project, strict=True)
    locked_candidate = project.get_locked_repository().candidates["zipp"]
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
    monkeypatch.setattr("pdm.project.lockfile.Lockfile.spec_version", parse_version("4.1.1"))
    project.lockfile._data["metadata"]["lock_version"] = lock_version
    assert project.lockfile.compatibility() == expected
    result = pdm(["lock", "--check"], obj=project)
    assert result.exit_code == (1 if expected == Compatibility.NONE else 0)


def test_lock_default_inherit_metadata(project, pdm, mocker, working_set):
    project.add_dependencies(["requests"])
    pdm(["lock"], obj=project, strict=True)
    assert "inherit_metadata" in project.lockfile.strategy
    packages = project.lockfile["package"]
    assert all(package["groups"] == ["default"] for package in packages)

    resolver = mocker.patch.object(project, "get_resolver")
    pdm(["sync"], obj=project, strict=True)
    resolver.assert_not_called()
    for key in ("requests", "idna", "chardet", "urllib3"):
        assert key in working_set


def test_lock_inherit_metadata_strategy(project, pdm, mocker, working_set):
    project.add_dependencies(["requests"])
    pdm(["lock", "-S", "inherit_metadata"], obj=project, strict=True)
    assert "inherit_metadata" in project.lockfile.strategy
    packages = project.lockfile["package"]
    assert all(package["groups"] == ["default"] for package in packages)

    resolver = mocker.patch.object(project, "get_resolver")
    pdm(["sync"], obj=project, strict=True)
    resolver.assert_not_called()
    for key in ("requests", "idna", "chardet", "urllib3"):
        assert key in working_set


def test_lock_exclude_newer(project, pdm):
    project.pyproject.metadata["requires-python"] = ">=3.9"
    project.project_config["pypi.url"] = "https://my.pypi.org/json"
    project.add_dependencies(["zipp"])
    pdm(["lock", "--exclude-newer", "2024-01-01"], obj=project, strict=True, cleanup=False)
    assert project.get_locked_repository().candidates["zipp"].version == "3.6.0"

    pdm(["lock"], obj=project, strict=True, cleanup=False)
    assert project.get_locked_repository().candidates["zipp"].version == "3.7.0"


exclusion_cases = [
    pytest.param(("-G", ":all", "--without", "tz,ssl"), id="-G :all --without tz,ssl"),
    pytest.param(("-G", ":all", "--without", "tz", "--without", "ssl"), id="-G :all --without tz --without ssl"),
    pytest.param(("--with", ":all", "--without", "tz,ssl"), id="--with all --without tz,ssl"),
    pytest.param(("--with", ":all", "--without", "tz", "--without", "ssl"), id="--with all --without tz --without ssl"),
    pytest.param(("--without", "tz", "--without", "ssl"), id="--without tz --without ssl"),
    pytest.param(("--without", "tz,ssl"), id="--without tz,ssl"),
]


@pytest.mark.parametrize("args", exclusion_cases)
@pytest.mark.usefixtures("repository")
def test_lock_all_with_excluded_groups(project, pdm, args):
    project.add_dependencies(["urllib3"], "url")
    project.add_dependencies(["pytz"], "tz", True)
    project.add_dependencies(["pyopenssl"], "ssl")
    pdm(["lock", *args], obj=project, strict=True)
    assert "urllib3" in project.get_locked_repository().candidates
    assert "pytz" not in project.get_locked_repository().candidates
    assert "pyopenssl" not in project.get_locked_repository().candidates


@pytest.mark.parametrize(
    "args",
    [
        ("--append",),
        ("--python", "<3.6"),
        ("-S", "cross_platform", "--append", "--python", "3.10"),
        ("--platform", "linux", "--refresh"),
    ],
)
def test_forbidden_lock_target_options(project, pdm, args):
    result = pdm(["lock", *args], obj=project)
    assert result.exit_code != 0
    assert "PdmUsageError" in result.stderr


@pytest.mark.parametrize("nested", [False, True])
def test_lock_for_multiple_targets(project, pdm, repository, nested):
    deps = [
        'django<2; sys_platform == "win32"',
        'django>=2; sys_platform != "win32"',
    ]
    if nested:
        repository.add_candidate("foo", "0.1.0")
        repository.add_dependencies("foo", "0.1.0", deps)
        project.add_dependencies(["foo"])
    else:
        project.add_dependencies(deps)

    pdm(["lock", "--platform", "windows"], obj=project, strict=True)
    locked = project.get_locked_repository()
    candidates = locked.all_candidates
    assert len(candidates["django"]) == 1
    assert candidates["django"][0].version == "1.11.8"
    assert len(locked.targets) == 1
    pytz = candidates["pytz"][0]
    assert str(pytz.req.marker) == 'sys_platform == "win32"'

    result = pdm(["lock", "--platform", "windows", "--append"], obj=project, strict=True)
    assert "already exists, skip locking." in result.stdout

    pdm(["lock", "--platform", "linux", "--append"], obj=project, strict=True)
    locked = project.get_locked_repository()
    candidates = locked.all_candidates
    assert len(locked.targets) == 2
    assert sorted(c.version for c in candidates["django"]) == ["1.11.8", "2.2.9"]
    pytz = candidates["pytz"][0]
    assert not pytz.req.marker or pytz.req.marker.is_any()

    # not append but overwrite
    pdm(["lock", "--platform", "windows"], obj=project, strict=True)
    locked = project.get_locked_repository()
    candidates = locked.all_candidates
    assert len(candidates["django"]) == 1
    assert candidates["django"][0].version == "1.11.8"
    assert len(locked.targets) == 1
    pytz = candidates["pytz"][0]
    assert str(pytz.req.marker) == 'sys_platform == "win32"'


CONSTRAINT_FILE = str(FIXTURES / "constraints.txt")


@pytest.mark.usefixtures("repository")
@pytest.mark.parametrize("constraint", [CONSTRAINT_FILE, path_to_url(CONSTRAINT_FILE)])
def test_lock_with_override_file(project, pdm, constraint):
    project.add_dependencies(["requests"])
    pdm(["lock", "--override", constraint], obj=project, strict=True)
    candidates = project.get_locked_repository().candidates
    assert candidates["requests"].version == "2.20.0b1"
    assert candidates["urllib3"].version == "1.23b0"
    assert "django" not in candidates
