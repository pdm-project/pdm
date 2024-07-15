import tarfile
import zipfile
from unittest import mock

import pytest

from pdm.cli.commands.build import Command

pytestmark = pytest.mark.usefixtures("local_finder")


def get_tarball_names(path):
    with tarfile.open(path, "r:gz") as tar:
        return tar.getnames()


def get_wheel_names(path):
    with zipfile.ZipFile(path) as zf:
        return zf.namelist()


def test_build_command(project, pdm, mocker):
    do_build = mocker.patch.object(Command, "do_build")
    # prevent the context_settings from being reset
    project.core.exit_stack.pop_all()
    pdm(["build", "--no-sdist", "-Ca=1", "--config-setting", "b=2"], obj=project)
    do_build.assert_called_with(
        project,
        sdist=False,
        wheel=True,
        dest=mock.ANY,
        clean=True,
        hooks=mock.ANY,
    )
    assert project.core.state.config_settings == {"a": "1", "b": "2"}


def test_build_global_project_forbidden(pdm):
    result = pdm(["build", "-g"])
    assert result.exit_code != 0


def test_build_single_module(fixture_project):
    project = fixture_project("demo-module")

    Command.do_build(project)
    tar_names = get_tarball_names(project.root / "dist/demo_module-0.1.0.tar.gz")
    for name in [
        "foo_module.py",
        "bar_module.py",
        "LICENSE",
        "pyproject.toml",
        "PKG-INFO",
    ]:
        assert f"demo_module-0.1.0/{name}" in tar_names

    for i in range(2):
        if i == 1:
            Command.do_build(project, sdist=False)
        zip_names = get_wheel_names(project.root / "dist/demo_module-0.1.0-py3-none-any.whl")
        for name in ["foo_module.py", "bar_module.py"]:
            assert name in zip_names

        for name in ("pyproject.toml", "LICENSE"):
            assert name not in zip_names


def test_build_single_module_with_readme(fixture_project):
    project = fixture_project("demo-module")
    project.pyproject.metadata["readme"] = "README.md"
    project.pyproject.write()
    Command.do_build(project)
    assert "demo_module-0.1.0/README.md" in get_tarball_names(project.root / "dist/demo_module-0.1.0.tar.gz")


def test_build_package(fixture_project):
    project = fixture_project("demo-package")
    Command.do_build(project)

    tar_names = get_tarball_names(project.root / "dist/my_package-0.1.0.tar.gz")
    assert "my_package-0.1.0/my_package/__init__.py" in tar_names
    assert "my_package-0.1.0/my_package/data.json" in tar_names
    assert "my_package-0.1.0/single_module.py" not in tar_names
    assert "my_package-0.1.0/data_out.json" not in tar_names

    zip_names = get_wheel_names(project.root / "dist/my_package-0.1.0-py3-none-any.whl")
    assert "my_package/__init__.py" in zip_names
    assert "my_package/data.json" in zip_names
    assert "single_module.py" not in zip_names
    assert "data_out.json" not in zip_names


def test_build_src_package(fixture_project):
    project = fixture_project("demo-src-package")
    Command.do_build(project)

    tar_names = get_tarball_names(project.root / "dist/demo_package-0.1.0.tar.gz")
    assert "demo_package-0.1.0/src/my_package/__init__.py" in tar_names
    assert "demo_package-0.1.0/src/my_package/data.json" in tar_names

    zip_names = get_wheel_names(project.root / "dist/demo_package-0.1.0-py3-none-any.whl")
    assert "my_package/__init__.py" in zip_names
    assert "my_package/data.json" in zip_names


def test_build_package_include(fixture_project):
    project = fixture_project("demo-package")
    build_config = project.pyproject.settings.setdefault("build", {})
    build_config["includes"] = [
        "my_package/",
        "single_module.py",
        "data_out.json",
    ]
    build_config["excludes"] = ["my_package/*.json"]
    project.pyproject.write()
    Command.do_build(project)

    tar_names = get_tarball_names(project.root / "dist/my_package-0.1.0.tar.gz")
    assert "my_package-0.1.0/my_package/__init__.py" in tar_names
    assert "my_package-0.1.0/my_package/data.json" not in tar_names
    assert "my_package-0.1.0/single_module.py" in tar_names
    assert "my_package-0.1.0/data_out.json" in tar_names

    zip_names = get_wheel_names(project.root / "dist/my_package-0.1.0-py3-none-any.whl")
    assert "my_package/__init__.py" in zip_names
    assert "my_package/data.json" not in zip_names
    assert "single_module.py" in zip_names
    assert "data_out.json" in zip_names


def test_build_src_package_by_include(fixture_project):
    project = fixture_project("demo-src-package")
    project.pyproject.settings.setdefault("build", {})["includes"] = ["src/my_package"]
    project.pyproject.write()
    Command.do_build(project)

    tar_names = get_tarball_names(project.root / "dist/demo_package-0.1.0.tar.gz")
    assert "demo_package-0.1.0/src/my_package/__init__.py" in tar_names
    assert "demo_package-0.1.0/src/my_package/data.json" in tar_names

    zip_names = get_wheel_names(project.root / "dist/demo_package-0.1.0-py3-none-any.whl")
    assert "my_package/__init__.py" in zip_names
    assert "my_package/data.json" in zip_names


def test_build_with_config_settings(fixture_project):
    project = fixture_project("demo-src-package")
    project.core.state.config_settings = {"--plat-name": "win_amd64"}
    Command.do_build(project)

    assert (project.root / "dist/demo_package-0.1.0-py3-none-win_amd64.whl").exists()


def test_cli_build_with_config_settings(fixture_project, pdm):
    project = fixture_project("demo-src-package")
    result = pdm(["build", "-C--plat-name=win_amd64"], obj=project)
    assert result.exit_code == 0
    assert (project.root / "dist/demo_package-0.1.0-py3-none-win_amd64.whl").exists()


@pytest.mark.usefixtures("local_finder")
def test_build_with_no_isolation(pdm, project):
    result = pdm(["build", "--no-isolation"], obj=project)
    assert result.exit_code == 1
    pdm(["add", "pdm-backend", "--no-self"], obj=project, strict=True)
    result = pdm(["build", "--no-isolation"], obj=project)
    assert result.exit_code == 0


def test_build_ignoring_pip_environment(fixture_project, monkeypatch):
    project = fixture_project("demo-module")
    monkeypatch.setenv("PIP_REQUIRE_VIRTUALENV", "1")
    Command.do_build(project)
