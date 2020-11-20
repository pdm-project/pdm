import sys
from collections import namedtuple

import pytest
from distlib.wheel import Wheel

from pdm.cli import actions
from pdm.exceptions import PdmException, PdmUsageError
from pdm.models.requirements import parse_requirement
from pdm.project import Project
from tests.conftest import Distribution

Requirement = namedtuple("Requirement", "key")


def make_distribution(name, version):
    req = Requirement(name)
    return Distribution(req.key, version)


def test_sync_only_different(project, repository, working_set, capsys):
    working_set.add_distribution(make_distribution("foo", "0.1.0"))
    working_set.add_distribution(make_distribution("chardet", "3.0.1"))
    working_set.add_distribution(make_distribution("idna", "2.7"))
    actions.do_add(project, packages=["requests"])
    out, _ = capsys.readouterr()
    assert "4 to add" in out
    assert "1 to update" in out
    assert "foo" in working_set
    assert "test-project" in working_set
    assert working_set["chardet"].version == "3.0.4"


def test_sync_in_sequential_mode(project, repository, working_set, capsys):
    project.project_config["parallel_install"] = False
    actions.do_add(project, packages=["requests"])
    out, _ = capsys.readouterr()
    assert "6 to add" in out
    assert "test-project" in working_set
    assert working_set["chardet"].version == "3.0.4"


def test_sync_no_lockfile(project):
    project.add_dependencies({"requests": parse_requirement("requests")})
    with pytest.raises(PdmException):
        actions.do_sync(project)


def test_sync_clean_packages(project, repository, working_set):
    for candidate in [
        make_distribution("foo", "0.1.0"),
        make_distribution("chardet", "3.0.1"),
        make_distribution("idna", "2.7"),
    ]:
        working_set.add_distribution(candidate)
    actions.do_add(project, packages=["requests"], sync=False)
    actions.do_sync(project, clean=True)
    assert "foo" not in working_set


def test_sync_dry_run(project, repository, working_set):
    for candidate in [
        make_distribution("foo", "0.1.0"),
        make_distribution("chardet", "3.0.1"),
        make_distribution("idna", "2.7"),
    ]:
        working_set.add_distribution(candidate)
    actions.do_add(project, packages=["requests"], sync=False)
    actions.do_sync(project, clean=True, dry_run=True)
    assert "foo" in working_set
    assert "requests" not in working_set
    assert working_set["chardet"].version == "3.0.1"


def test_add_package(project, repository, working_set, is_dev):
    actions.do_add(project, is_dev, packages=["requests"])
    section = "dev-dependencies" if is_dev else "dependencies"

    assert project.tool_settings[section]["requests"] == "<3.0.0,>=2.19.1"
    locked_candidates = project.get_locked_candidates("dev" if is_dev else "default")
    assert locked_candidates["idna"].version == "2.7"
    for package in ("requests", "idna", "chardet", "urllib3", "certifi"):
        assert package in working_set


def test_add_package_to_custom_package(project, repository, working_set):
    actions.do_add(project, section="test", packages=["requests"])

    assert "requests" in project.tool_settings["test-dependencies"]
    locked_candidates = project.get_locked_candidates("test")
    assert locked_candidates["idna"].version == "2.7"
    for package in ("requests", "idna", "chardet", "urllib3", "certifi"):
        assert package in working_set


def test_add_editable_package(project, repository, working_set, is_dev, vcs):
    # Ensure that correct python version is used.
    actions.do_use(project, sys.executable)
    actions.do_add(
        project,
        is_dev,
        editables=["git+https://github.com/test-root/demo.git#egg=demo"],
    )
    section = "dev-dependencies" if is_dev else "dependencies"
    assert "demo" in project.tool_settings[section]
    locked_candidates = project.get_locked_candidates("dev" if is_dev else "default")
    assert locked_candidates["idna"].version == "2.7"
    assert "idna" in working_set


def test_add_no_install(project, repository, working_set):
    actions.do_add(project, sync=False, packages=["requests"])
    for package in ("requests", "idna", "chardet", "urllib3", "certifi"):
        assert package not in working_set


def test_add_package_save_exact(project, repository):
    actions.do_add(project, sync=False, save="exact", packages=["requests"])
    assert project.tool_settings["dependencies"]["requests"] == "==2.19.1"


def test_add_package_save_wildcard(project, repository):
    actions.do_add(project, sync=False, save="wildcard", packages=["requests"])
    assert project.tool_settings["dependencies"]["requests"] == "*"


def test_add_package_update_reuse(project, repository):
    actions.do_add(project, sync=False, save="wildcard", packages=["requests", "pytz"])

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
    actions.do_add(
        project, sync=False, save="wildcard", packages=["requests"], strategy="reuse"
    )
    locked_candidates = project.get_locked_candidates()
    assert locked_candidates["requests"].version == "2.20.0"
    assert locked_candidates["chardet"].version == "3.0.4"
    assert locked_candidates["pytz"].version == "2019.3"


def test_add_package_update_eager(project, repository):
    actions.do_add(project, sync=False, save="wildcard", packages=["requests", "pytz"])

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
    actions.do_add(
        project, sync=False, save="wildcard", packages=["requests"], strategy="eager"
    )
    locked_candidates = project.get_locked_candidates()
    assert locked_candidates["requests"].version == "2.20.0"
    assert locked_candidates["chardet"].version == "3.0.5"
    assert locked_candidates["pytz"].version == "2019.3"


def test_update_all_packages(project, repository, working_set, capsys):
    actions.do_add(project, packages=["requests", "pytz"])
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
    actions.do_update(project)
    locked_candidates = project.get_locked_candidates()
    assert locked_candidates["requests"].version == "2.20.0"
    assert locked_candidates["chardet"].version == "3.0.5"
    assert locked_candidates["pytz"].version == "2019.6"
    out, _ = capsys.readouterr()
    assert "3 to update" in out

    actions.do_sync(project)
    out, _ = capsys.readouterr()
    assert "All packages are synced to date" in out


def test_update_specified_packages(project, repository, working_set):
    actions.do_add(project, sync=False, packages=["requests", "pytz"])
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
    actions.do_update(project, packages=["requests"])
    locked_candidates = project.get_locked_candidates()
    assert locked_candidates["requests"].version == "2.20.0"
    assert locked_candidates["chardet"].version == "3.0.4"


def test_update_specified_packages_eager_mode(project, repository, working_set):
    actions.do_add(project, sync=False, packages=["requests", "pytz"])
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
    actions.do_update(project, strategy="eager", packages=["requests"])
    locked_candidates = project.get_locked_candidates()
    assert locked_candidates["requests"].version == "2.20.0"
    assert locked_candidates["chardet"].version == "3.0.5"
    assert locked_candidates["pytz"].version == "2019.3"


def test_remove_package(project, repository, working_set, is_dev):
    actions.do_add(project, dev=is_dev, packages=["requests", "pytz"])
    actions.do_remove(project, dev=is_dev, packages=["pytz"])
    locked_candidates = project.get_locked_candidates()
    assert "pytz" not in locked_candidates
    assert "pytz" not in working_set


def test_remove_package_no_sync(project, repository, working_set):
    actions.do_add(project, packages=["requests", "pytz"])
    actions.do_remove(project, sync=False, packages=["pytz"])
    locked_candidates = project.get_locked_candidates()
    assert "pytz" not in locked_candidates
    assert "pytz" in working_set


def test_remove_package_not_exist(project, repository, working_set):
    actions.do_add(project, packages=["requests", "pytz"])
    with pytest.raises(PdmException):
        actions.do_remove(project, sync=False, packages=["django"])


def test_remove_package_exist_in_multi_section(project, repository, working_set):
    actions.do_add(project, packages=["requests"])
    actions.do_add(project, dev=True, packages=["urllib3"])
    actions.do_remove(project, dev=True, packages=["urllib3"])
    assert "urllib3" not in project.tool_settings["dev-dependencies"]
    assert "urllib3" in working_set
    assert "requests" in working_set


def test_add_remove_no_package(project, repository):
    with pytest.raises(PdmUsageError):
        actions.do_add(project, packages=())

    with pytest.raises(PdmUsageError):
        actions.do_remove(project, packages=())


def test_update_with_package_and_sections_argument(project, repository, working_set):
    actions.do_add(project, packages=["requests", "pytz"])
    with pytest.raises(PdmUsageError):
        actions.do_update(project, sections=("default", "dev"), packages=("requests",))

    with pytest.raises(PdmUsageError):
        actions.do_update(project, default=False, packages=("requests",))


def test_add_package_with_mismatch_marker(project, repository, working_set, mocker):
    mocker.patch(
        "pdm.models.environment.get_pep508_environment",
        return_value={"platform_system": "Darwin"},
    )
    actions.do_add(project, packages=["requests", "pytz; platform_system!='Darwin'"])
    assert "pytz" not in working_set


def test_add_dependency_from_multiple_parents(project, repository, working_set, mocker):
    mocker.patch(
        "pdm.models.environment.get_pep508_environment",
        return_value={"platform_system": "Darwin"},
    )
    actions.do_add(project, packages=["requests", "chardet; platform_system!='Darwin'"])
    assert "chardet" in working_set


def test_list_packages(capsys):
    actions.do_list(Project())
    out, _ = capsys.readouterr()
    assert "pdm" in out
    assert "tomlkit" in out
    assert "pip" in out


def test_lock_dependencies(project, repository):
    project.add_dependencies({"requests": parse_requirement("requests")})
    actions.do_lock(project)
    assert project.lockfile_file.exists()
    locked = project.get_locked_candidates()
    for package in ("requests", "idna", "chardet", "certifi"):
        assert package in locked


def test_build_distributions(tmp_path):
    project = Project()
    actions.do_build(project, dest=tmp_path.as_posix())
    wheel = Wheel(next(tmp_path.glob("*.whl")).as_posix())
    assert wheel.name == "pdm"
    tarball = next(tmp_path.glob("*.tar.gz"))
    assert tarball.exists()


def test_project_no_init_error(project_no_init):

    for handler in (
        actions.do_add,
        actions.do_build,
        actions.do_list,
        actions.do_lock,
        actions.do_update,
    ):
        with pytest.raises(
            PdmException, match="The pyproject.toml has not been initialized yet"
        ):
            handler(project_no_init)


def test_list_dependency_graph(project, capsys, repository, working_set):
    actions.do_add(project, packages=["requests"])
    actions.do_list(project, True)
    content, _ = capsys.readouterr()
    assert "└── urllib3 1.22 [ required: <1.24,>=1.21.1 ]" in content


def test_list_dependency_graph_with_circular(project, capsys, repository, working_set):
    repository.add_candidate("foo", "0.1.0")
    repository.add_candidate("foo-bar", "0.1.0")
    repository.add_dependencies("foo", "0.1.0", ["foo-bar"])
    repository.add_dependencies("foo-bar", "0.1.0", ["foo"])
    actions.do_add(project, packages=["foo"])
    actions.do_list(project, True)
    content, _ = capsys.readouterr()
    assert "foo [circular]" in content


def test_list_reverse_without_graph_flag(project):
    with pytest.raises(PdmException):
        actions.do_list(project, reverse=True)


def test_list_reverse_dependency_graph(project, capsys, repository, working_set):
    actions.do_add(project, packages=["requests"])
    actions.do_list(project, True, True)
    content, _ = capsys.readouterr()
    assert "└── requests 2.19.1 [ requires: <1.24,>=1.21.1 ]" in content


def test_update_unconstrained_without_packages(project, repository, working_set):
    actions.do_add(project, packages=("requests",))
    with pytest.raises(PdmUsageError):
        actions.do_update(project, unconstrained=True)


def test_update_ignore_constraints(project, repository, working_set):
    actions.do_add(project, packages=("pytz",))
    assert project.tool_settings["dependencies"]["pytz"] == "<2020.0.0,>=2019.3"
    repository.add_candidate("pytz", "2020.2")

    actions.do_update(project, unconstrained=False, packages=("pytz",))
    assert project.tool_settings["dependencies"]["pytz"] == "<2020.0.0,>=2019.3"
    assert project.get_locked_candidates()["pytz"].version == "2019.3"

    actions.do_update(project, unconstrained=True, packages=("pytz",))
    assert project.tool_settings["dependencies"]["pytz"] == "<2021.0.0,>=2020.2"
    assert project.get_locked_candidates()["pytz"].version == "2020.2"


def test_init_validate_python_requires(project_no_init):
    with pytest.raises(ValueError):
        actions.do_init(project_no_init, python_requires="3.7")
