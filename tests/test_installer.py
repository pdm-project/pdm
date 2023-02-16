import logging
import os

import pytest
from unearth import Link

from pdm.installers import InstallManager
from pdm.models.candidates import Candidate
from pdm.models.requirements import parse_requirement
from pdm.utils import fs_supports_symlink
from tests import FIXTURES

pytestmark = pytest.mark.usefixtures("local_finder")


def test_install_wheel_with_inconsistent_dist_info(project):
    req = parse_requirement("pyfunctional")
    candidate = Candidate(
        req,
        link=Link("http://fixtures.test/artifacts/PyFunctional-1.4.3-py3-none-any.whl"),
    )
    installer = InstallManager(project.environment)
    installer.install(candidate)
    assert "pyfunctional" in project.environment.get_working_set()


def test_install_with_file_existing(project):
    req = parse_requirement("demo")
    candidate = Candidate(
        req,
        link=Link("http://fixtures.test/artifacts/demo-0.0.1-py2.py3-none-any.whl"),
    )
    (project.environment.packages_path / "lib/demo.py").touch()
    installer = InstallManager(project.environment)
    installer.install(candidate)


def test_uninstall_commit_rollback(project):
    req = parse_requirement("demo")
    candidate = Candidate(
        req,
        link=Link("http://fixtures.test/artifacts/demo-0.0.1-py2.py3-none-any.whl"),
    )
    installer = InstallManager(project.environment)
    lib_path = project.environment.get_paths()["purelib"]
    installer.install(candidate)
    lib_file = os.path.join(lib_path, "demo.py")
    assert os.path.exists(lib_file)
    remove_paths = installer.get_paths_to_remove(project.environment.get_working_set()["demo"])
    remove_paths.remove()
    assert not os.path.exists(lib_file)
    remove_paths.rollback()
    assert os.path.exists(lib_file)


def test_rollback_after_commit(project, caplog):
    caplog.set_level(logging.ERROR, logger="pdm.termui")
    req = parse_requirement("demo")
    candidate = Candidate(
        req,
        link=Link("http://fixtures.test/artifacts/demo-0.0.1-py2.py3-none-any.whl"),
    )
    installer = InstallManager(project.environment)
    lib_path = project.environment.get_paths()["purelib"]
    installer.install(candidate)
    lib_file = os.path.join(lib_path, "demo.py")
    assert os.path.exists(lib_file)
    remove_paths = installer.get_paths_to_remove(project.environment.get_working_set()["demo"])
    remove_paths.remove()
    remove_paths.commit()
    assert not os.path.exists(lib_file)
    caplog.clear()
    remove_paths.rollback()
    assert not os.path.exists(lib_file)

    assert any(record.message == "Can't rollback, not uninstalled yet" for record in caplog.records)


@pytest.mark.parametrize("use_install_cache", [False, True])
def test_uninstall_with_console_scripts(project, use_install_cache):
    req = parse_requirement("celery")
    candidate = Candidate(
        req,
        link=Link("http://fixtures.test/artifacts/celery-4.4.2-py2.py3-none-any.whl"),
    )
    installer = InstallManager(project.environment, use_install_cache=use_install_cache)
    installer.install(candidate)
    celery_script = os.path.join(
        project.environment.get_paths()["scripts"],
        "celery.exe" if os.name == "nt" else "celery",
    )
    assert os.path.exists(celery_script)
    installer.uninstall(project.environment.get_working_set()["celery"])
    assert not os.path.exists(celery_script)


def test_install_wheel_with_cache(project, invoke):
    supports_symlink = fs_supports_symlink()
    req = parse_requirement("future-fstrings")
    candidate = Candidate(
        req,
        link=Link("http://fixtures.test/artifacts/future_fstrings-1.2.0-py2.py3-none-any.whl"),
    )
    installer = InstallManager(project.environment, use_install_cache=True)
    installer.install(candidate)

    lib_path = project.environment.get_paths()["purelib"]
    if supports_symlink:
        assert os.path.islink(os.path.join(lib_path, "future_fstrings.py"))
        assert os.path.islink(os.path.join(lib_path, "aaaaa_future_fstrings.pth"))
    else:
        assert os.path.isfile(os.path.join(lib_path, "aaa_future_fstrings.pth"))
        assert os.path.isfile(os.path.join(lib_path, "aaaaa_future_fstrings.pth"))

    cache_path = project.cache("packages") / "future_fstrings-1.2.0-py2.py3-none-any"
    assert cache_path.is_dir()
    r = invoke(["run", "python", "-c", "import future_fstrings"], obj=project)
    assert r.exit_code == 0

    dist = project.environment.get_working_set()["future-fstrings"]
    installer.uninstall(dist)
    if supports_symlink:
        assert not os.path.exists(os.path.join(lib_path, "future_fstrings.py"))
        assert not os.path.exists(os.path.join(lib_path, "aaaaa_future_fstrings.pth"))
    else:
        assert not os.path.isfile(os.path.join(lib_path, "aaa_future_fstrings.pth"))
        assert not os.path.isfile(os.path.join(lib_path, "aaaaa_future_fstrings.pth"))
    assert not dist.read_text("direct_url.json")
    assert not cache_path.exists()


def test_url_requirement_is_not_cached(project):
    req = parse_requirement(
        "future-fstrings @ http://fixtures.test/artifacts/future_fstrings-1.2.0-py2.py3-none-any.whl"
    )
    candidate = Candidate(req)
    installer = InstallManager(project.environment, use_install_cache=True)
    installer.install(candidate)
    cache_path = project.cache("packages") / "future_fstrings-1.2.0-py2.py3-none-any"
    assert not cache_path.is_dir()
    lib_path = project.environment.get_paths()["purelib"]
    assert os.path.isfile(os.path.join(lib_path, "future_fstrings.py"))
    assert os.path.isfile(os.path.join(lib_path, "aaaaa_future_fstrings.pth"))
    dist = project.environment.get_working_set()["future-fstrings"]
    assert dist.read_text("direct_url.json")


@pytest.mark.parametrize("use_install_cache", [False, True])
def test_install_wheel_with_data_scripts(project, use_install_cache):
    req = parse_requirement("jmespath")
    candidate = Candidate(
        req,
        link=Link("http://fixtures.test/artifacts/jmespath-0.10.0-py2.py3-none-any.whl"),
    )
    installer = InstallManager(project.environment, use_install_cache=use_install_cache)
    installer.install(candidate)
    bin_path = os.path.join(project.environment.get_paths()["scripts"], "jp.py")
    assert os.path.isfile(bin_path)
    if os.name != "nt":
        assert os.stat(bin_path).st_mode & 0o100

    dist = project.environment.get_working_set()["jmespath"]
    installer.uninstall(dist)
    assert not os.path.exists(bin_path)


def test_compress_file_list_for_rename():
    from pdm.installers.uninstallers import compress_for_rename

    project_root = str(FIXTURES / "projects")

    paths = {
        "test-removal/subdir",
        "test-removal/subdir/__init__.py",
        "test-removal/__init__.py",
        "test-removal/bar.py",
        "test-removal/foo.py",
        "test-removal/non_exist.py",
    }
    abs_paths = {os.path.join(project_root, path) for path in paths}
    assert sorted(compress_for_rename(abs_paths)) == [os.path.join(project_root, "test-removal" + os.sep)]
