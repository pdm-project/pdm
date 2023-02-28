import pytest

from pdm.cli import actions
from pdm.models.requirements import parse_requirement
from pdm.pytest import Distribution
from pdm.utils import cd


def test_sync_packages_with_group_all(project, working_set, pdm):
    project.add_dependencies({"requests": parse_requirement("requests")})
    project.add_dependencies({"pytz": parse_requirement("pytz")}, "date")
    project.add_dependencies({"pyopenssl": parse_requirement("pyopenssl")}, "ssl")
    pdm(["install", "-G:all"], obj=project, strict=True)
    assert "pytz" in working_set
    assert "requests" in working_set
    assert "idna" in working_set
    assert "pyopenssl" in working_set


def test_sync_packages_with_all_dev(project, working_set, pdm):
    project.add_dependencies({"requests": parse_requirement("requests")})
    project.add_dependencies({"pytz": parse_requirement("pytz")}, "date", True)
    project.add_dependencies({"pyopenssl": parse_requirement("pyopenssl")}, "ssl", True)
    pdm(["install", "-d", "--no-default"], obj=project, strict=True)
    assert "requests" not in working_set
    assert "idna" not in working_set
    assert "pytz" in working_set
    assert "pyopenssl" in working_set


def test_sync_no_lockfile(project, pdm):
    project.add_dependencies({"requests": parse_requirement("requests")})
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
    project.add_dependencies({"requests": parse_requirement("requests")})
    project.add_dependencies({"pytz": parse_requirement("pytz")}, "date")
    pdm(["install", "-Gdate"], obj=project, strict=True)
    assert "pytz" in working_set
    assert "requests" in working_set
    assert "idna" in working_set


@pytest.mark.parametrize("prod_option", [("--prod",), ()])
def test_sync_production_packages(project, working_set, prod_option, pdm):
    project.add_dependencies({"requests": parse_requirement("requests")})
    project.add_dependencies({"pytz": parse_requirement("pytz")}, "dev", dev=True)
    pdm(["install", *prod_option], obj=project, strict=True)
    assert "requests" in working_set
    assert ("pytz" in working_set) == (not prod_option)


def test_sync_without_self(project, working_set, pdm):
    project.add_dependencies({"requests": parse_requirement("requests")})
    pdm(["install", "--no-self"], obj=project, strict=True)
    assert project.name not in working_set, list(working_set)


def test_sync_with_index_change(project, index, pdm):
    project.project_config["pypi.url"] = "https://my.pypi.org/simple"
    project.pyproject.metadata["requires-python"] = ">=3.6"
    project.pyproject.metadata["dependencies"] = ["future-fstrings"]
    project.pyproject.write()
    index[
        "/simple/future-fstrings/"
    ] = b"""
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
    pdm(["lock"], obj=project, strict=True)
    file_hashes = project.lockfile["metadata"]["files"]["future-fstrings 1.2.0"]
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
    assert "Lock file" not in result.stderr

    project.add_dependencies({"pytz": parse_requirement("pytz")}, "default")
    result = pdm(["install"], obj=project)
    assert "Lock file hash doesn't match" in result.stderr
    assert "pytz" in project.locked_repository.all_candidates
    assert project.is_lockfile_hash_match()


def test_install_with_dry_run(project, pdm, repository):
    project.add_dependencies({"pytz": parse_requirement("pytz")}, "default")
    result = pdm(["install", "--dry-run"], obj=project)
    project.lockfile.reload()
    assert "pytz" not in project.locked_repository.all_candidates
    assert "pytz 2019.3" in result.output


def test_install_check(pdm, project, repository):
    result = pdm(["install", "--check"], obj=project)
    assert result.exit_code == 1

    result = pdm(["add", "requests", "--no-sync"], obj=project)
    project.add_dependencies({"requests": parse_requirement("requests>=2.0")})
    result = pdm(["install", "--check"], obj=project)
    assert result.exit_code == 1


def test_sync_with_only_keep_option(project, working_set, pdm):
    project.add_dependencies({"requests": parse_requirement("requests>=2.0")})
    project.add_dependencies({"django": parse_requirement("django")}, "web", True)
    pdm(["install"], obj=project, strict=True)
    assert all(p in working_set for p in ("requests", "urllib3", "django", "pytz")), list(working_set)
    pdm(["sync", "--prod", "--only-keep"], obj=project, strict=True)
    assert "requests" in working_set
    assert "urllib3" in working_set
    assert "django" not in working_set


def test_install_referencing_self_package(project, working_set, pdm):
    project.add_dependencies({"pytz": parse_requirement("pytz")}, to_group="tz")
    project.add_dependencies({"urllib3": parse_requirement("urllib3")}, to_group="web")
    project.add_dependencies({"test-project": parse_requirement("test-project[tz,web]")}, to_group="all")
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
    project.project_config["install.parallel"] = True
    pdm(["add", "certifi", "chardet", "pytz", "--no-sync"], obj=project)

    handler = mocker.patch(
        "pdm.installers.synchronizers.Synchronizer.install_candidate",
        side_effect=RuntimeError,
    )
    mocker.patch("multiprocessing.cpu_count", return_value=1)
    result = pdm(["install", "--fail-fast"], obj=project)
    assert result.exit_code == 1
    handler.assert_has_calls(
        [
            mocker.call("certifi", mocker.ANY),
            mocker.call("chardet", mocker.ANY),
        ],
        any_order=True,
    )


@pytest.mark.usefixtures("working_set")
def test_install_groups_not_in_lockfile(project, pdm):
    project.add_dependencies({"pytz": parse_requirement("pytz")}, to_group="tz")
    project.add_dependencies({"urllib3": parse_requirement("urllib3")}, to_group="web")
    pdm(["install", "-vv"], obj=project, strict=True)
    assert project.lockfile.groups == ["default"]
    all_locked_packages = project.locked_repository.all_candidates
    for package in ["pytz", "urllib3"]:
        assert package not in all_locked_packages
    with pytest.raises(RuntimeError, match="Requested groups not in lockfile"):
        pdm(["install", "-Gtz"], obj=project, strict=True)


def test_install_locked_groups(project, pdm, working_set):
    project.add_dependencies({"urllib3": parse_requirement("urllib3")})
    project.add_dependencies({"pytz": parse_requirement("pytz")}, to_group="tz")
    pdm(["lock", "-Gtz", "--no-default"], obj=project, strict=True)
    pdm(["sync"], obj=project, strict=True)
    assert "pytz" in working_set
    assert "urllib3" not in working_set


def test_install_groups_and_lock(project, pdm, working_set):
    project.add_dependencies({"urllib3": parse_requirement("urllib3")})
    project.add_dependencies({"pytz": parse_requirement("pytz")}, to_group="tz")
    pdm(["install", "-Gtz", "--no-default"], obj=project, strict=True)
    assert "pytz" in working_set
    assert "urllib3" not in working_set
    assert project.lockfile.groups == ["tz"]
    assert "pytz" in project.locked_repository.all_candidates
    assert "urllib3" not in project.locked_repository.all_candidates
