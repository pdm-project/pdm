import pytest

from pdm.cli import actions
from pdm.models.markers import EnvSpec
from pdm.pytest import Distribution
from pdm.utils import cd


def test_sync_packages_with_group_all(project, working_set, pdm):
    project.add_dependencies(["requests"])
    project.add_dependencies(["pytz"], "date")
    project.add_dependencies(["pyopenssl"], "ssl")
    pdm(["install", "-G:all"], obj=project, strict=True)
    assert "pytz" in working_set
    assert "requests" in working_set
    assert "idna" in working_set
    assert "pyopenssl" in working_set


def test_sync_packages_with_all_dev(project, working_set, pdm):
    project.add_dependencies(["requests"])
    project.add_dependencies(["pytz"], "date", True)
    project.add_dependencies(["pyopenssl"], "ssl", True)
    pdm(["install", "-d", "--no-default"], obj=project, strict=True)
    assert "requests" not in working_set
    assert "idna" not in working_set
    assert "pytz" in working_set
    assert "pyopenssl" in working_set


def test_sync_no_lockfile(project, pdm):
    project.add_dependencies(["requests"])
    result = pdm(["sync"], obj=project)
    assert result.exit_code == 1


def test_sync_clean_packages(project, working_set, pdm):
    for candidate in [
        Distribution("foo", "0.1.0"),
        Distribution("chardet", "3.0.1"),
        Distribution("idna", "2.7"),
    ]:
        working_set.add_distribution(candidate)
    pdm(["add", "--no-sync", "requests"], obj=project, strict=True)
    pdm(["sync", "--clean"], obj=project, strict=True)
    assert "foo" not in working_set


def test_sync_dry_run(project, working_set, pdm):
    for candidate in [
        Distribution("foo", "0.1.0"),
        Distribution("chardet", "3.0.1"),
        Distribution("idna", "2.7"),
    ]:
        working_set.add_distribution(candidate)
    pdm(["add", "--no-sync", "requests"], obj=project, strict=True)
    pdm(["sync", "--clean", "--dry-run"], obj=project, strict=True)
    assert "foo" in working_set
    assert "requests" not in working_set
    assert working_set["chardet"].version == "3.0.1"


def test_sync_only_different(project, working_set, pdm):
    working_set.add_distribution(Distribution("foo", "0.1.0"))
    working_set.add_distribution(Distribution("chardet", "3.0.1"))
    working_set.add_distribution(Distribution("idna", "2.7"))
    result = pdm(["add", "requests"], obj=project, strict=True)
    out = result.stdout
    assert "3 to add" in out, out
    assert "1 to update" in out
    assert "foo" in working_set
    assert "test-project" in working_set, list(working_set)
    assert working_set["chardet"].version == "3.0.4"


def test_sync_in_sequential_mode(project, working_set, pdm):
    project.project_config["install.parallel"] = False
    result = pdm(["add", "requests"], obj=project, strict=True)
    assert "5 to add" in result.stdout
    assert "test-project" in working_set
    assert working_set["chardet"].version == "3.0.4"


def test_sync_packages_with_groups(project, working_set, pdm):
    project.add_dependencies(["requests"])
    project.add_dependencies(["pytz"], "date")
    pdm(["install", "-Gdate"], obj=project, strict=True)
    assert "pytz" in working_set
    assert "requests" in working_set
    assert "idna" in working_set


@pytest.mark.parametrize("prod_option", [("--prod",), ()])
def test_sync_production_packages(project, working_set, prod_option, pdm):
    project.add_dependencies(["requests"])
    project.add_dependencies(["pytz"], "dev", dev=True)
    pdm(["install", *prod_option], obj=project, strict=True)
    assert "requests" in working_set
    assert ("pytz" in working_set) == (not prod_option)


def test_sync_without_self(project, working_set, pdm):
    project.add_dependencies(["requests"])
    pdm(["install", "--no-self"], obj=project, strict=True)
    assert project.name not in working_set, list(working_set)


def test_sync_with_index_change(project, index, pdm):
    project.project_config["pypi.url"] = "https://my.pypi.org/simple"
    project.pyproject.metadata["requires-python"] = ">=3.6"
    project.pyproject.metadata["dependencies"] = ["future-fstrings"]
    project.pyproject.write()
    index["/simple/future-fstrings/"] = b"""
    <html>
    <body>
        <h1>future-fstrings</h1>
        <a href="http://fixtures.test/artifacts/future_fstrings-1.2.0-py2.py3-none-any\
.whl#sha256=90e49598b553d8746c4dc7d9442e0359d038c3039d802c91c0a55505da318c63">
        future_fstrings-1.2.0.tar.gz
        </a>
    </body>
    </html>
    """
    pdm(["lock"], obj=project, strict=True, cleanup=False)
    file_hashes = project.lockfile["package"][0]["files"]
    assert [e["hash"] for e in file_hashes] == [
        "sha256:90e49598b553d8746c4dc7d9442e0359d038c3039d802c91c0a55505da318c63"
    ]
    # Mimic the CDN inconsistences of PyPI simple index. See issues/596.
    del index["/simple/future-fstrings/"]
    pdm(["sync", "--no-self"], obj=project, strict=True)


def test_install_command(project, pdm, mocker):
    do_lock = mocker.patch.object(actions, "do_lock")
    do_sync = mocker.patch.object(actions, "do_sync")
    pdm(["install"], obj=project)
    do_lock.assert_called_once()
    do_sync.assert_called_once()


def test_sync_command(project, pdm, mocker):
    pdm(["lock"], obj=project)
    do_sync = mocker.patch.object(actions, "do_sync")
    pdm(["sync"], obj=project)
    do_sync.assert_called_once()


@pytest.mark.usefixtures("working_set")
def test_install_with_lockfile(project, pdm):
    result = pdm(["lock", "-v"], obj=project)
    assert result.exit_code == 0
    result = pdm(["install"], obj=project)
    assert "Lockfile" not in result.stderr

    project.add_dependencies(["pytz"], "default")
    result = pdm(["install"], obj=project)
    assert "Lockfile hash doesn't match" in result.stderr
    assert "pytz" in project.get_locked_repository().candidates
    assert project.is_lockfile_hash_match()


def test_install_with_dry_run(project, pdm, repository):
    project.add_dependencies(["pytz"], "default")
    result = pdm(["install", "--dry-run"], obj=project)
    project.lockfile.reload()
    assert "pytz" not in project.get_locked_repository().candidates
    assert "pytz 2019.3" in result.output


def test_install_frozen_lockfile(project, pdm, working_set):
    project.add_dependencies(["requests"], "default")
    result = pdm(["install", "--frozen-lockfile"], obj=project)
    assert result.exit_code == 0
    assert not project.lockfile.exists()
    assert "urllib3" in working_set
    assert "requests" in working_set


def test_install_no_lock_deprecated(project, pdm, working_set):
    project.add_dependencies(["requests"], "default")
    result = pdm(["install", "--no-lock"], obj=project)
    assert result.exit_code == 0
    assert not project.lockfile.exists()
    assert "urllib3" in working_set
    assert "requests" in working_set
    assert "WARNING: --no-lock is deprecated" in result.stderr


def test_install_check(pdm, project, repository):
    result = pdm(["install", "--check"], obj=project)
    assert result.exit_code == 1

    result = pdm(["add", "requests", "--no-sync"], obj=project)
    project.add_dependencies(["requests>=2.0"])
    result = pdm(["install", "--check"], obj=project)
    assert result.exit_code == 1


def test_sync_with_clean_unselected_option(project, working_set, pdm):
    project.add_dependencies(["requests>=2.0"])
    project.add_dependencies(["django"], "web", True)
    pdm(["install"], obj=project, strict=True)
    assert all(p in working_set for p in ("requests", "urllib3", "django", "pytz")), list(working_set)
    pdm(["sync", "--prod", "--clean-unselected"], obj=project, strict=True)
    assert "requests" in working_set
    assert "urllib3" in working_set
    assert "django" not in working_set


def test_install_referencing_self_package(project, working_set, pdm):
    project.add_dependencies(["pytz"], to_group="tz")
    project.add_dependencies(["urllib3"], to_group="web")
    project.add_dependencies(["test-project[tz,web]"], to_group="all")
    pdm(["install", "-Gall"], obj=project, strict=True)
    assert "pytz" in working_set
    assert "urllib3" in working_set


def test_install_monorepo_with_rel_paths(fixture_project, pdm, working_set):
    project = fixture_project("test-monorepo")
    with cd(project.root):
        pdm(["install"], obj=project, strict=True)
    for package in ("package-a", "package-b", "core"):
        assert package in working_set


@pytest.mark.usefixtures("repository")
def test_install_retry(project, pdm, mocker):
    pdm(["add", "certifi", "chardet", "--no-sync"], obj=project)
    handler = mocker.patch(
        "pdm.installers.synchronizers.Synchronizer.install_candidate",
        side_effect=RuntimeError,
    )
    result = pdm(["install"], obj=project)
    assert result.exit_code == 1
    handler.assert_has_calls(
        [
            mocker.call("certifi", mocker.ANY),
            mocker.call("chardet", mocker.ANY),
            mocker.call("certifi", mocker.ANY),
            mocker.call("chardet", mocker.ANY),
        ],
        any_order=True,
    )


@pytest.mark.usefixtures("repository")
def test_install_fail_fast(project, pdm, mocker):
    project.project_config["install.parallel"] = False
    pdm(["add", "certifi", "chardet", "pytz", "--no-sync"], obj=project)

    handler = mocker.patch(
        "pdm.installers.synchronizers.Synchronizer.install_candidate",
        side_effect=RuntimeError,
    )
    result = pdm(["install", "--fail-fast"], obj=project)
    assert result.exit_code == 1
    assert handler.call_count == 1


@pytest.mark.usefixtures("working_set")
def test_install_groups_not_in_lockfile(project, pdm):
    project.add_dependencies(["pytz"], to_group="tz")
    project.add_dependencies(["urllib3"], to_group="web")
    pdm(["install", "-vv"], obj=project, strict=True)
    assert project.lockfile.groups == ["default"]
    all_locked_packages = project.get_locked_repository().candidates
    for package in ["pytz", "urllib3"]:
        assert package not in all_locked_packages
    with pytest.raises(RuntimeError, match="Requested groups not in lockfile"):
        pdm(["install", "-Gtz"], obj=project, strict=True)


def test_install_locked_groups(project, pdm, working_set):
    project.add_dependencies(["urllib3"])
    project.add_dependencies(["pytz"], to_group="tz")
    pdm(["lock", "-Gtz", "--no-default"], obj=project, strict=True)
    pdm(["sync"], obj=project, strict=True)
    assert "pytz" in working_set
    assert "urllib3" not in working_set


def test_install_groups_and_lock(project, pdm, working_set):
    project.add_dependencies(["urllib3"])
    project.add_dependencies(["pytz"], to_group="tz")
    pdm(["install", "-Gtz", "--no-default"], obj=project, strict=True)
    assert "pytz" in working_set
    assert "urllib3" not in working_set
    assert project.lockfile.groups == ["tz"]
    assert "pytz" in project.get_locked_repository().candidates
    assert "urllib3" not in project.get_locked_repository().candidates


def test_install_requirement_with_extras(project, pdm, working_set):
    project.add_dependencies(["requests==2.19.1"])
    project.add_dependencies(["requests[socks]"], to_group="socks")
    pdm(["lock", "-Gsocks"], obj=project, strict=True)
    pdm(["sync", "-Gsocks"], obj=project, strict=True)
    assert "pysocks" in working_set


def test_fix_package_type_and_update(fixture_project, pdm, working_set):
    project = fixture_project("test-package-type-fixer")
    pdm(["fix", "package-type"], obj=project, strict=True)
    pdm(["update"], obj=project, strict=True)
    assert "test-package-type-fixer" not in working_set


exclusion_cases = [
    pytest.param(("-G", ":all", "--without", "tz,ssl"), id="-G :all --without tz,ssl"),
    pytest.param(("-G", ":all", "--without", "tz", "--without", "ssl"), id="-G :all --without tz --without ssl"),
    pytest.param(("--with", ":all", "--without", "tz,ssl"), id="--with all --without tz,ssl"),
    pytest.param(("--with", ":all", "--without", "tz", "--without", "ssl"), id="--with all --without tz --without ssl"),
    pytest.param(("--without", "tz", "--without", "ssl"), id="--without tz --without ssl"),
    pytest.param(("--without", "tz,ssl"), id="--without tz,ssl"),
]


@pytest.mark.parametrize("args", exclusion_cases)
def test_install_all_with_excluded_groups(project, working_set, pdm, args):
    project.add_dependencies(["urllib3"], "url")
    project.add_dependencies(["pytz"], "tz", True)
    project.add_dependencies(["pyopenssl"], "ssl")
    pdm(["install", *args], obj=project, strict=True)
    assert "urllib3" in working_set
    assert "pytz" not in working_set
    assert "pyopenssl" not in working_set


@pytest.mark.parametrize("args", exclusion_cases)
def test_sync_all_with_excluded_groups(project, working_set, pdm, args):
    project.add_dependencies(["urllib3"], "url")
    project.add_dependencies(["pytz"], "tz", True)
    project.add_dependencies(["pyopenssl"], "ssl")
    pdm(["lock", "-G:all"], obj=project, strict=True)
    pdm(["sync", *args], obj=project, strict=True)
    assert "urllib3" in working_set
    assert "pytz" not in working_set
    assert "pyopenssl" not in working_set


def test_excluded_groups_ignored_if_prod_passed(project, working_set, pdm):
    project.add_dependencies(["urllib3"], "url")
    project.add_dependencies(["pytz"], "tz")
    project.add_dependencies(["pyopenssl"], "ssl")
    pdm(["install", "--prod", "--without", "ssl"], obj=project, strict=True)
    assert "urllib3" not in working_set
    assert "pytz" not in working_set
    assert "pyopenssl" not in working_set


def test_excluded_groups_ignored_if_dev_passed(project, working_set, pdm):
    project.add_dependencies(["urllib3"], "url")
    project.add_dependencies(["pytz"], "tz")
    project.add_dependencies(["pyopenssl"], "ssl")
    pdm(["install", "--dev", "--without", "ssl"], obj=project, strict=True)
    assert "urllib3" not in working_set
    assert "pytz" not in working_set
    assert "pyopenssl" not in working_set


@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("groups", [("default",), None])
def test_install_from_multi_target_lock(project, pdm, repository, nested, groups):
    from pdm.cli.actions import resolve_candidates_from_lockfile

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
    pdm(["lock", "--platform", "linux", "--append"], obj=project, strict=True)

    candidates = resolve_candidates_from_lockfile(
        project, project.get_dependencies(), env_spec=EnvSpec.from_spec("==3.11", "windows"), groups=groups
    )
    assert candidates["django"].version == "1.11.8"
    assert "sqlparse" not in candidates

    candidates = resolve_candidates_from_lockfile(
        project, project.get_dependencies(), env_spec=EnvSpec.from_spec("==3.11", "linux"), groups=groups
    )
    assert candidates["django"].version == "2.2.9"
    assert "sqlparse" in candidates


def test_install_from_lock_with_higher_version(project, pdm, working_set):
    project.add_dependencies(["django"])
    pdm(["lock", "--platform", "manylinux_2_20_x86_64"], obj=project, strict=True)
    # linux is an alias for manylinux_2_17_x86_64 which is lower than the target
    project.environment.__dict__["spec"] = EnvSpec.from_spec("==3.11", "linux")
    result = pdm(["install"], obj=project)
    assert result.exit_code == 0
    assert "WARNING: Found lock target" in result.stderr


def test_install_from_lock_with_lower_version(project, pdm, working_set):
    project.add_dependencies(["django"])
    pdm(["lock", "--platform", "linux"], obj=project, strict=True)
    project.environment.__dict__["spec"] = EnvSpec.from_spec("==3.11", "manylinux_2_20_x86_64")
    result = pdm(["install"], obj=project)
    assert result.exit_code == 0


@pytest.mark.parametrize(
    "python,platform", [("==3.11", "macos"), ("==3.10", "manylinux_2_17_x86_64"), ("==3.11", "manylinux_2_17_aarch64")]
)
@pytest.mark.parametrize("python_option", ["3.11", ">=3.11"])
def test_install_from_lock_with_incompatible_targets(project, pdm, python, platform, python_option):
    pdm(["lock", "--platform", "linux", "--python", python_option], obj=project, strict=True)
    project.environment.__dict__["spec"] = EnvSpec.from_spec(python, platform)
    result = pdm(["install"], obj=project)
    assert result.exit_code == 1
    assert "No compatible lock target found" in result.stderr
