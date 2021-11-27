import pytest

from pdm.cli import actions
from pdm.exceptions import PdmError
from pdm.models.requirements import parse_requirement
from tests.conftest import Distribution


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


def test_sync_no_lockfile(project):
    project.add_dependencies({"requests": parse_requirement("requests")})
    with pytest.raises(PdmError):
        actions.do_sync(project)


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
    assert "4 to add" in out, out
    assert "1 to update" in out
    assert "foo" in working_set
    assert "test-project" in working_set
    assert working_set["chardet"].version == "3.0.4"


@pytest.mark.usefixtures("repository")
def test_sync_in_sequential_mode(project, working_set, capsys):
    project.project_config["parallel_install"] = False
    actions.do_add(project, packages=["requests"])
    out, _ = capsys.readouterr()
    assert "6 to add" in out
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
    assert project.meta.name not in working_set


def test_sync_with_index_change(project, index):
    project.meta["requires-python"] = ">=3.6"
    project.meta["dependencies"] = ["future-fstrings"]
    project.write_pyproject()
    index[
        "future-fstrings"
    ] = """
    <html>
    <body>
        <h1>future-fstrings</h1>
        <a href="http://fixtures.test/artifacts/future_fstrings-1.2.0.tar.gz\
#sha256=6cf41cbe97c398ab5a81168ce0dbb8ad95862d3caf23c21e4430627b90844089">
        future_fstrings-1.2.0.tar.gz
        </a>
    </body>
    </html>
    """.encode()
    actions.do_lock(project)
    file_hashes = project.lockfile["metadata"]["files"]["future-fstrings 1.2.0"]
    assert [e["hash"] for e in file_hashes] == [
        "sha256:6cf41cbe97c398ab5a81168ce0dbb8ad95862d3caf23c21e4430627b90844089"
    ]
    # Mimic the CDN inconsistences of PyPI simple index. See issues/596.
    del index["future-fstrings"]
    actions.do_sync(project, no_self=True)
