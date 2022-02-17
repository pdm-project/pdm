import shutil
from pathlib import Path

import pytest

from pdm.cli import actions
from pdm.models.pip_shims import Link
from pdm.models.specifiers import PySpecSet
from tests import FIXTURES


@pytest.mark.usefixtures("repository")
def test_add_package(project, working_set, is_dev):
    actions.do_add(project, is_dev, packages=["requests"])
    group = (
        project.tool_settings["dev-dependencies"]["dev"]
        if is_dev
        else project.meta["dependencies"]
    )

    assert group[0] == "requests~=2.19"
    locked_candidates = project.locked_repository.all_candidates
    assert locked_candidates["idna"].version == "2.7"
    for package in ("requests", "idna", "chardet", "urllib3", "certifi"):
        assert package in working_set


def test_add_command(project, invoke, mocker):
    do_add = mocker.patch.object(actions, "do_add")
    invoke(["add", "requests"], obj=project)
    do_add.assert_called_once()


@pytest.mark.usefixtures("repository")
def test_add_package_to_custom_group(project, working_set):
    actions.do_add(project, group="test", packages=["requests"])

    assert "requests" in project.meta.optional_dependencies["test"][0]
    locked_candidates = project.locked_repository.all_candidates
    assert locked_candidates["idna"].version == "2.7"
    for package in ("requests", "idna", "chardet", "urllib3", "certifi"):
        assert package in working_set


@pytest.mark.usefixtures("repository")
def test_add_package_to_custom_dev_group(project, working_set):
    actions.do_add(project, dev=True, group="test", packages=["requests"])

    dependencies = project.tool_settings["dev-dependencies"]["test"]
    assert "requests" in dependencies[0]
    locked_candidates = project.locked_repository.all_candidates
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
    group = (
        project.tool_settings["dev-dependencies"]["dev"]
        if is_dev
        else project.meta["dependencies"]
    )
    assert "demo" in group[0]
    assert "-e git+https://github.com/test-root/demo.git#egg=demo" in group[1]
    locked_candidates = project.locked_repository.all_candidates
    assert (
        locked_candidates["demo"].prepare(project.environment).revision
        == "1234567890abcdef"
    )
    assert locked_candidates["idna"].version == "2.7"
    assert "idna" in working_set

    actions.do_sync(project, no_editable=True)
    assert not working_set["demo"].link_file


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
    assert working_set["demo"].link_file


@pytest.mark.usefixtures("repository", "working_set")
def test_add_remote_package_url(project, is_dev):
    project.environment.python_requires = PySpecSet(">=3.6")
    actions.do_add(
        project,
        is_dev,
        packages=["http://fixtures.test/artifacts/demo-0.0.1-py2.py3-none-any.whl"],
    )
    group = (
        project.tool_settings["dev-dependencies"]["dev"]
        if is_dev
        else project.meta["dependencies"]
    )
    assert (
        group[0]
        == "demo @ http://fixtures.test/artifacts/demo-0.0.1-py2.py3-none-any.whl"
    )


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


@pytest.mark.usefixtures("repository")
def test_add_package_save_minimum(project):
    actions.do_add(project, sync=False, save="minimum", packages=["requests"])
    assert project.meta.dependencies[0] == "requests>=2.19.1"


def test_add_package_update_reuse(project, repository):
    actions.do_add(project, sync=False, save="wildcard", packages=["requests", "pytz"])

    locked_candidates = project.locked_repository.all_candidates
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
    locked_candidates = project.locked_repository.all_candidates
    assert locked_candidates["requests"].version == "2.20.0"
    assert locked_candidates["chardet"].version == "3.0.4"
    assert locked_candidates["pytz"].version == "2019.3"


def test_add_package_update_eager(project, repository):
    actions.do_add(project, sync=False, save="wildcard", packages=["requests", "pytz"])

    locked_candidates = project.locked_repository.all_candidates
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
    locked_candidates = project.locked_repository.all_candidates
    assert locked_candidates["requests"].version == "2.20.0"
    assert locked_candidates["chardet"].version == "3.0.5"
    assert locked_candidates["pytz"].version == "2019.3"


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
def test_add_packages_without_self(project, working_set):
    project.environment.python_requires = PySpecSet(">=3.6")
    actions.do_add(project, packages=["requests"], no_self=True)
    assert project.meta.name not in working_set


@pytest.mark.usefixtures("repository", "working_set")
def test_add_package_unconstrained_rewrite_specifier(project):
    project.environment.python_requires = PySpecSet(">=3.6")
    actions.do_add(project, packages=["django"], no_self=True)
    locked_candidates = project.locked_repository.all_candidates
    assert locked_candidates["django"].version == "2.2.9"
    assert project.meta.dependencies[0] == "django~=2.2"

    actions.do_add(
        project, packages=["django-toolbar"], no_self=True, unconstrained=True
    )
    locked_candidates = project.locked_repository.all_candidates
    assert locked_candidates["django"].version == "1.11.8"
    assert project.meta.dependencies[0] == "django~=1.11"


@pytest.mark.usefixtures("repository", "working_set", "vcs")
def test_add_cached_vcs_requirement(project, mocker):
    project.environment.python_requires = PySpecSet(">=3.6")
    url = "git+https://github.com/test-root/demo.git@1234567890abcdef#egg=demo"
    built_path = FIXTURES / "artifacts/demo-0.0.1-py2.py3-none-any.whl"
    wheel_cache = project.make_wheel_cache()
    cache_path = Path(wheel_cache.get_path_for_link(Link(url)))
    if not cache_path.exists():
        cache_path.mkdir(parents=True)
    shutil.copy2(built_path, cache_path)
    downloader = mocker.patch("pdm.models.pip_shims.unpack_url")
    builder = mocker.patch("pdm.builders.WheelBuilder.build")
    actions.do_add(project, packages=[url], no_self=True)
    lockfile_entry = next(p for p in project.lockfile["package"] if p["name"] == "demo")
    assert lockfile_entry["revision"] == "1234567890abcdef"
    downloader.assert_not_called()
    builder.assert_not_called()


@pytest.mark.usefixtures("repository")
def test_add_with_dry_run(project, capsys):
    actions.do_add(project, dry_run=True, packages=["requests"])
    out, _ = capsys.readouterr()
    assert not project.get_dependencies()
    assert "requests 2.19.1" in out
    assert "urllib3 1.22" in out


@pytest.mark.usefixtures("repository")
def test_add_with_prerelease(project, working_set):
    actions.do_add(project, packages=["urllib3"], prerelease=True)
    assert working_set["urllib3"].version == "1.23b0"
    assert project.meta.dependencies[0] == "urllib3<2,>=1.23b0"
