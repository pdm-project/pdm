import pytest
from distlib.wheel import Wheel

from pdm.cli import actions
from pdm.exceptions import PdmException, PdmUsageError
from pdm.models.requirements import parse_requirement
from pdm.models.specifiers import PySpecSet


@pytest.mark.usefixtures("repository")
def test_add_package(project, working_set, is_dev):
    actions.do_add(project, is_dev, packages=["requests"])
    section = (
        project.tool_settings["dev-dependencies"]["dev"]
        if is_dev
        else project.meta["dependencies"]
    )

    assert section[0] == "requests~=2.19"
    locked_candidates = project.get_locked_candidates("dev" if is_dev else "default")
    assert locked_candidates["idna"].version == "2.7"
    for package in ("requests", "idna", "chardet", "urllib3", "certifi"):
        assert package in working_set


@pytest.mark.usefixtures("repository")
def test_add_package_to_custom_section(project, working_set):
    actions.do_add(project, section="test", packages=["requests"])

    assert "requests" in project.meta.optional_dependencies["test"][0]
    locked_candidates = project.get_locked_candidates("test")
    assert locked_candidates["idna"].version == "2.7"
    for package in ("requests", "idna", "chardet", "urllib3", "certifi"):
        assert package in working_set


@pytest.mark.usefixtures("repository")
def test_add_package_to_custom_dev_section(project, working_set):
    actions.do_add(project, dev=True, section="test", packages=["requests"])

    dependencies = project.tool_settings["dev-dependencies"]["test"]
    assert "requests" in dependencies[0]
    locked_candidates = project.get_locked_candidates("test")
    assert locked_candidates["idna"].version == "2.7"
    for package in ("requests", "idna", "chardet", "urllib3", "certifi"):
        assert package in working_set


@pytest.mark.usefixtures("repository", "vcs")
def test_add_editable_package(project, working_set, is_dev):
    # Ensure that correct python version is used.
    project.environment.python_requires = PySpecSet(">=3.6")
    actions.do_add(project, is_dev, packages=["demo"])
    actions.do_add(
        project,
        is_dev,
        editables=["git+https://github.com/test-root/demo.git#egg=demo"],
    )
    section = (
        project.tool_settings["dev-dependencies"]["dev"]
        if is_dev
        else project.meta["dependencies"]
    )
    assert "demo" in section[0]
    assert "-e git+https://github.com/test-root/demo.git#egg=demo" in section[1]
    locked_candidates = project.get_locked_candidates("dev" if is_dev else "default")
    assert locked_candidates["demo"].revision == "1234567890abcdef"
    assert locked_candidates["idna"].version == "2.7"
    assert "idna" in working_set


@pytest.mark.usefixtures("repository", "working_set")
def test_add_remote_package_url(project, is_dev):
    actions.do_add(
        project,
        is_dev,
        packages=["http://fixtures.test/artifacts/demo-0.0.1-py2.py3-none-any.whl"],
    )
    section = (
        project.tool_settings["dev-dependencies"]["dev"]
        if is_dev
        else project.meta["dependencies"]
    )
    assert (
        section[0]
        == "demo @ http://fixtures.test/artifacts/demo-0.0.1-py2.py3-none-any.whl"
    )


@pytest.mark.usefixtures("repository", "working_set", "vcs")
def test_remove_both_normal_and_editable_packages(project, is_dev):
    project.environment.python_requires = PySpecSet(">=3.6")
    actions.do_add(project, is_dev, packages=["demo"])
    actions.do_add(
        project,
        is_dev,
        editables=["git+https://github.com/test-root/demo.git#egg=demo"],
    )
    section = (
        project.tool_settings["dev-dependencies"]["dev"]
        if is_dev
        else project.meta["dependencies"]
    )
    actions.do_remove(project, is_dev, packages=["demo"])
    assert not section
    assert "demo" not in project.get_locked_candidates("dev" if is_dev else "default")


@pytest.mark.usefixtures("repository")
def test_add_no_install(project, working_set):
    actions.do_add(project, sync=False, packages=["requests"])
    for package in ("requests", "idna", "chardet", "urllib3", "certifi"):
        assert package not in working_set


@pytest.mark.usefixtures("repository")
def test_add_package_save_exact(project):
    actions.do_add(project, sync=False, save="exact", packages=["requests"])
    assert project.meta.dependencies[0] == "requests==2.19.1"


@pytest.mark.usefixtures("repository")
def test_add_package_save_wildcard(project):
    actions.do_add(project, sync=False, save="wildcard", packages=["requests"])
    assert project.meta.dependencies[0] == "requests"


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


@pytest.mark.usefixtures("working_set")
def test_update_all_packages(project, repository, capsys):
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


@pytest.mark.usefixtures("working_set")
def test_update_dry_run(project, repository, capsys):
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
    actions.do_update(project, dry_run=True)
    project.lockfile = None
    locked_candidates = project.get_locked_candidates()
    assert locked_candidates["requests"].version == "2.19.1"
    assert locked_candidates["chardet"].version == "3.0.4"
    assert locked_candidates["pytz"].version == "2019.3"
    out, _ = capsys.readouterr()
    assert "requests 2.19.1 -> 2.20.0" in out


@pytest.mark.usefixtures("working_set")
def test_update_top_packages_dry_run(project, repository, capsys):
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
    actions.do_update(project, top=True, dry_run=True)
    out, _ = capsys.readouterr()
    assert "requests 2.19.1 -> 2.20.0" in out
    assert "- chardet 3.0.4 -> 3.0.5" not in out


@pytest.mark.usefixtures("working_set")
def test_update_specified_packages(project, repository):
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


@pytest.mark.usefixtures("working_set")
def test_update_specified_packages_eager_mode(project, repository):
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


@pytest.mark.usefixtures("repository")
def test_remove_package(project, working_set, is_dev):
    actions.do_add(project, dev=is_dev, packages=["requests", "pytz"])
    actions.do_remove(project, dev=is_dev, packages=["pytz"])
    locked_candidates = project.get_locked_candidates()
    assert "pytz" not in locked_candidates
    assert "pytz" not in working_set


@pytest.mark.usefixtures("repository")
def test_remove_package_no_sync(project, working_set):
    actions.do_add(project, packages=["requests", "pytz"])
    actions.do_remove(project, sync=False, packages=["pytz"])
    locked_candidates = project.get_locked_candidates()
    assert "pytz" not in locked_candidates
    assert "pytz" in working_set


@pytest.mark.usefixtures("repository", "working_set")
def test_remove_package_not_exist(project):
    actions.do_add(project, packages=["requests", "pytz"])
    with pytest.raises(PdmException):
        actions.do_remove(project, sync=False, packages=["django"])


@pytest.mark.usefixtures("repository")
def test_remove_package_exist_in_multi_section(project, working_set):
    actions.do_add(project, packages=["requests"])
    actions.do_add(project, dev=True, packages=["urllib3"])
    actions.do_remove(project, dev=True, packages=["urllib3"])
    assert all(
        "urllib3" not in line
        for line in project.tool_settings["dev-dependencies"]["dev"]
    )
    assert "urllib3" in working_set
    assert "requests" in working_set


@pytest.mark.usefixtures("repository")
def test_add_remove_no_package(project):
    with pytest.raises(PdmUsageError):
        actions.do_add(project, packages=())

    with pytest.raises(PdmUsageError):
        actions.do_remove(project, packages=())


@pytest.mark.usefixtures("repository", "working_set")
def test_update_with_package_and_sections_argument(project):
    actions.do_add(project, packages=["requests", "pytz"])
    with pytest.raises(PdmUsageError):
        actions.do_update(project, sections=("default", "dev"), packages=("requests",))

    with pytest.raises(PdmUsageError):
        actions.do_update(project, default=False, packages=("requests",))


@pytest.mark.usefixtures("repository")
def test_add_package_with_mismatch_marker(project, working_set, mocker):
    mocker.patch(
        "pdm.models.environment.get_pep508_environment",
        return_value={"platform_system": "Darwin"},
    )
    actions.do_add(project, packages=["requests", "pytz; platform_system!='Darwin'"])
    assert "pytz" not in working_set


@pytest.mark.usefixtures("repository")
def test_add_dependency_from_multiple_parents(project, working_set, mocker):
    mocker.patch(
        "pdm.models.environment.get_pep508_environment",
        return_value={"platform_system": "Darwin"},
    )
    actions.do_add(project, packages=["requests", "chardet; platform_system!='Darwin'"])
    assert "chardet" in working_set


@pytest.mark.usefixtures("repository")
def test_lock_dependencies(project):
    project.add_dependencies({"requests": parse_requirement("requests")})
    actions.do_lock(project)
    assert project.lockfile_file.exists()
    locked = project.get_locked_candidates()
    for package in ("requests", "idna", "chardet", "certifi"):
        assert package in locked


def test_build_distributions(tmp_path, core):
    project = core.create_project()
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


@pytest.mark.usefixtures("repository", "working_set")
def test_list_dependency_graph(project, capsys):
    actions.do_add(project, packages=["requests"])
    actions.do_list(project, True)
    content, _ = capsys.readouterr()
    assert "└── urllib3 1.22 [ required: <1.24,>=1.21.1 ]" in content


@pytest.mark.usefixtures("working_set")
def test_list_dependency_graph_with_circular(project, capsys, repository):
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


@pytest.mark.usefixtures("repository", "working_set")
def test_list_reverse_dependency_graph(project, capsys):
    actions.do_add(project, packages=["requests"])
    actions.do_list(project, True, True)
    content, _ = capsys.readouterr()
    assert "└── requests 2.19.1 [ requires: <1.24,>=1.21.1 ]" in content


@pytest.mark.usefixtures("repository", "working_set")
def test_update_packages_with_top(project):
    actions.do_add(project, packages=("requests",))
    with pytest.raises(PdmUsageError):
        actions.do_update(project, packages=("requests",), top=True)


@pytest.mark.usefixtures("working_set")
def test_update_ignore_constraints(project, repository):
    actions.do_add(project, packages=("pytz",))
    assert project.meta.dependencies == ["pytz~=2019.3"]
    repository.add_candidate("pytz", "2020.2")

    actions.do_update(project, unconstrained=False, packages=("pytz",))
    assert project.meta.dependencies == ["pytz~=2019.3"]
    assert project.get_locked_candidates()["pytz"].version == "2019.3"

    actions.do_update(project, unconstrained=True, packages=("pytz",))
    assert project.meta.dependencies == ["pytz~=2020.2"]
    assert project.get_locked_candidates()["pytz"].version == "2020.2"


def test_init_validate_python_requires(project_no_init):
    with pytest.raises(ValueError):
        actions.do_init(project_no_init, python_requires="3.7")


@pytest.mark.usefixtures("repository", "vcs")
def test_editable_package_override_non_editable(project, working_set):
    project.environment.python_requires = PySpecSet(">=3.6")
    actions.do_add(
        project, packages=["git+https://github.com/test-root/demo.git#egg=demo"]
    )
    actions.do_add(
        project,
        editables=["git+https://github.com/test-root/demo.git#egg=demo"],
    )
    assert working_set["demo"].editable
