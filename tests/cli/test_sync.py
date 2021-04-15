import pytest

from pdm.cli import actions
from pdm.exceptions import PdmException
from pdm.models.requirements import parse_requirement
from tests.conftest import Distribution


@pytest.mark.usefixtures("repository")
def test_sync_packages_with_section_all(project, working_set):
    project.add_dependencies({"requests": parse_requirement("requests")})
    project.add_dependencies({"pytz": parse_requirement("pytz")}, "date")
    project.add_dependencies({"pyopenssl": parse_requirement("pyopenssl")}, "ssl")
    actions.do_lock(project)
    actions.do_sync(project, sections=[":all"])
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
    with pytest.raises(PdmException):
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
    assert "3 to add" in out
    assert "1 to update" in out
    assert "foo" in working_set
    assert "test-project" in working_set
    assert working_set["chardet"].version == "3.0.4"


@pytest.mark.usefixtures("repository")
def test_sync_in_sequential_mode(project, working_set, capsys):
    project.project_config["parallel_install"] = False
    actions.do_add(project, packages=["requests"])
    out, _ = capsys.readouterr()
    assert "5 to add" in out
    assert "test-project" in working_set
    assert working_set["chardet"].version == "3.0.4"


@pytest.mark.usefixtures("repository")
def test_sync_packages_with_sections(project, working_set):
    project.add_dependencies({"requests": parse_requirement("requests")})
    project.add_dependencies({"pytz": parse_requirement("pytz")}, "date")
    actions.do_lock(project)
    actions.do_sync(project, sections=["date"])
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
