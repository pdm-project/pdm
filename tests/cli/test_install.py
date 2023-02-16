import pytest

from pdm.cli import actions
from pdm.models.requirements import parse_requirement
from pdm.pytest import Distribution
from pdm.utils import cd


@pytest.mark.usefixtures("repository")
def test_sync_packages_with_group_all(project, working_set):
    project.add_dependencies({"requests": parse_requirement("requests")})
    project.add_dependencies({"pytz": parse_requirement("pytz")}, "date")
    project.add_dependencies({"pyopenssl": parse_requirement("pyopenssl")}, "ssl")
    actions.do_lock(project)
    actions.do_sync(project, groups=[":all"])
    assert "pytz" in working_set
    assert "requests" in working_set
    assert "idna" in working_set
    assert "pyopenssl" in working_set


@pytest.mark.usefixtures("repository")
def test_sync_packages_with_all_dev(project, working_set):
    project.add_dependencies({"requests": parse_requirement("requests")})
    project.add_dependencies({"pytz": parse_requirement("pytz")}, "date", True)
    project.add_dependencies({"pyopenssl": parse_requirement("pyopenssl")}, "ssl", True)
    actions.do_lock(project)
    actions.do_sync(project, dev=True, default=False)
    assert "requests" not in working_set
    assert "idna" not in working_set
    assert "pytz" in working_set
    assert "pyopenssl" in working_set


def test_sync_no_lockfile(project, invoke):
    project.add_dependencies({"requests": parse_requirement("requests")})
    result = invoke(["sync"], obj=project)
    assert result.exit_code == 1


@pytest.mark.usefixtures("repository")
def test_sync_clean_packages(project, working_set):
    for candidate in [
        Distribution("foo", "0.1.0"),
        Distribution("chardet", "3.0.1"),
        Distribution("idna", "2.7"),
    ]:
        working_set.add_distribution(candidate)
    actions.do_add(project, packages=["requests"], sync=False)
    actions.do_sync(project, clean=True)
    assert "foo" not in working_set


@pytest.mark.usefixtures("repository")
def test_sync_dry_run(project, working_set):
    for candidate in [
        Distribution("foo", "0.1.0"),
        Distribution("chardet", "3.0.1"),
        Distribution("idna", "2.7"),
    ]:
        working_set.add_distribution(candidate)
    actions.do_add(project, packages=["requests"], sync=False)
    actions.do_sync(project, clean=True, dry_run=True)
    assert "foo" in working_set
    assert "requests" not in working_set
    assert working_set["chardet"].version == "3.0.1"


@pytest.mark.usefixtures("repository")
def test_sync_only_different(project, working_set, capsys):
    working_set.add_distribution(Distribution("foo", "0.1.0"))
    working_set.add_distribution(Distribution("chardet", "3.0.1"))
    working_set.add_distribution(Distribution("idna", "2.7"))
    actions.do_add(project, packages=["requests"])
    out, _ = capsys.readouterr()
    assert "3 to add" in out, out
    assert "1 to update" in out
    assert "foo" in working_set
    assert "test-project" in working_set, list(working_set)
    assert working_set["chardet"].version == "3.0.4"


@pytest.mark.usefixtures("repository")
def test_sync_in_sequential_mode(project, working_set, capsys):
    project.project_config["install.parallel"] = False
    actions.do_add(project, packages=["requests"])
    out, _ = capsys.readouterr()
    assert "5 to add" in out
    assert "test-project" in working_set
    assert working_set["chardet"].version == "3.0.4"


@pytest.mark.usefixtures("repository")
def test_sync_packages_with_groups(project, working_set):
    project.add_dependencies({"requests": parse_requirement("requests")})
    project.add_dependencies({"pytz": parse_requirement("pytz")}, "date")
    actions.do_lock(project)
    actions.do_sync(project, groups=["date"])
    assert "pytz" in working_set
    assert "requests" in working_set
    assert "idna" in working_set


@pytest.mark.usefixtures("repository")
def test_sync_production_packages(project, working_set, is_dev):
    project.add_dependencies({"requests": parse_requirement("requests")})
    project.add_dependencies({"pytz": parse_requirement("pytz")}, "dev", dev=True)
    actions.do_lock(project)
    actions.do_sync(project, dev=is_dev)
    assert "requests" in working_set
    assert ("pytz" in working_set) == is_dev


@pytest.mark.usefixtures("repository")
def test_sync_without_self(project, working_set):
    project.add_dependencies({"requests": parse_requirement("requests")})
    actions.do_lock(project)
    actions.do_sync(project, no_self=True)
    assert project.name not in working_set, list(working_set)


def test_sync_with_index_change(project, index):
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
    actions.do_lock(project)
    file_hashes = project.lockfile["metadata"]["files"]["future-fstrings 1.2.0"]
    assert [e["hash"] for e in file_hashes] == [
        "sha256:90e49598b553d8746c4dc7d9442e0359d038c3039d802c91c0a55505da318c63"
    ]
    # Mimic the CDN inconsistences of PyPI simple index. See issues/596.
    del index["/simple/future-fstrings/"]
    actions.do_sync(project, no_self=True)


def test_install_command(project, invoke, mocker):
    do_lock = mocker.patch.object(actions, "do_lock")
    do_sync = mocker.patch.object(actions, "do_sync")
    invoke(["install"], obj=project)
    do_lock.assert_called_once()
    do_sync.assert_called_once()


def test_sync_command(project, invoke, mocker):
    invoke(["lock"], obj=project)
    do_sync = mocker.patch.object(actions, "do_sync")
    invoke(["sync"], obj=project)
    do_sync.assert_called_once()


def test_install_with_lockfile(project, invoke, working_set, repository):
    result = invoke(["lock", "-v"], obj=project)
    assert result.exit_code == 0
    result = invoke(["install"], obj=project)
    assert "Lock file" not in result.stderr

    project.add_dependencies({"pytz": parse_requirement("pytz")}, "default")
    result = invoke(["install"], obj=project)
    assert "Lock file hash doesn't match" in result.stderr
    assert "pytz" in project.locked_repository.all_candidates
    assert project.is_lockfile_hash_match()


def test_install_with_dry_run(project, invoke, repository):
    project.add_dependencies({"pytz": parse_requirement("pytz")}, "default")
    result = invoke(["install", "--dry-run"], obj=project)
    project.lockfile.reload()
    assert "pytz" not in project.locked_repository.all_candidates
    assert "pytz 2019.3" in result.output


def test_install_check(invoke, project, repository):
    result = invoke(["install", "--check"], obj=project)
    assert result.exit_code == 1

    result = invoke(["add", "requests", "--no-sync"], obj=project)
    project.add_dependencies({"requests": parse_requirement("requests>=2.0")})
    result = invoke(["install", "--check"], obj=project)
    assert result.exit_code == 1


@pytest.mark.usefixtures("repository")
def test_sync_with_pure_option(project, working_set, invoke):
    project.add_dependencies({"requests": parse_requirement("requests>=2.0")})
    project.add_dependencies({"django": parse_requirement("django")}, "web", True)
    invoke(["install"], obj=project, strict=True)
    assert all(p in working_set for p in ("requests", "urllib3", "django", "pytz")), list(working_set)
    actions.do_sync(project, dev=False, only_keep=True)
    assert "requests" in working_set
    assert "urllib3" in working_set
    assert "django" not in working_set


def test_install_referencing_self_package(project, working_set, invoke):
    project.add_dependencies({"pytz": parse_requirement("pytz")}, to_group="tz")
    project.add_dependencies({"urllib3": parse_requirement("urllib3")}, to_group="web")
    project.add_dependencies({"test-project": parse_requirement("test-project[tz,web]")}, to_group="all")
    invoke(["install", "-Gall"], obj=project, strict=True)
    assert "pytz" in working_set
    assert "urllib3" in working_set


def test_install_monorepo_with_rel_paths(fixture_project, invoke, working_set):
    project = fixture_project("test-monorepo")
    with cd(project.root):
        invoke(["install"], obj=project, strict=True)
    for package in ("package-a", "package-b", "core"):
        assert package in working_set
