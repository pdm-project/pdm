import tarfile
import zipfile

import pytest

from pdm.cli import actions

pytestmark = pytest.mark.usefixtures("local_finder")


def get_tarball_names(path):
    with tarfile.open(path, "r:gz") as tar:
        return tar.getnames()


def get_wheel_names(path):
    with zipfile.ZipFile(path) as zf:
        return zf.namelist()


def test_build_command(project, invoke, mocker):
    do_build = mocker.patch.object(actions, "do_build")
    invoke(["build"], obj=project)
    do_build.assert_called_once()


def test_build_global_project_forbidden(invoke):
    result = invoke(["build", "-g"])
    assert result.exit_code != 0


def test_build_single_module(fixture_project):
    project = fixture_project("demo-module")

    actions.do_build(project)
    tar_names = get_tarball_names(project.root / "dist/demo-module-0.1.0.tar.gz")
    for name in [
        "foo_module.py",
        "bar_module.py",
        "LICENSE",
        "pyproject.toml",
        "PKG-INFO",
    ]:
        assert f"demo-module-0.1.0/{name}" in tar_names

    zip_names = get_wheel_names(project.root / "dist/demo_module-0.1.0-py3-none-any.whl")
    for name in ["foo_module.py", "bar_module.py"]:
        assert name in zip_names

    for name in ("pyproject.toml", "LICENSE"):
        assert name not in zip_names


def test_build_single_module_with_readme(fixture_project):
    project = fixture_project("demo-module")
    project.pyproject.metadata["readme"] = "README.md"
    project.pyproject.write()
    actions.do_build(project)
    assert "demo-module-0.1.0/README.md" in get_tarball_names(project.root / "dist/demo-module-0.1.0.tar.gz")


def test_build_package(fixture_project):
    project = fixture_project("demo-package")
    actions.do_build(project)

    tar_names = get_tarball_names(project.root / "dist/demo-package-0.1.0.tar.gz")
    assert "demo-package-0.1.0/my_package/__init__.py" in tar_names
    assert "demo-package-0.1.0/my_package/data.json" in tar_names
    assert "demo-package-0.1.0/single_module.py" not in tar_names
    assert "demo-package-0.1.0/data_out.json" not in tar_names

    zip_names = get_wheel_names(project.root / "dist/demo_package-0.1.0-py3-none-any.whl")
    assert "my_package/__init__.py" in zip_names
    assert "my_package/data.json" in zip_names
    assert "single_module.py" not in zip_names
    assert "data_out.json" not in zip_names


def test_build_src_package(fixture_project):
    project = fixture_project("demo-src-package")
    actions.do_build(project)

    tar_names = get_tarball_names(project.root / "dist/demo-package-0.1.0.tar.gz")
    assert "demo-package-0.1.0/src/my_package/__init__.py" in tar_names
    assert "demo-package-0.1.0/src/my_package/data.json" in tar_names

    zip_names = get_wheel_names(project.root / "dist/demo_package-0.1.0-py3-none-any.whl")
    assert "my_package/__init__.py" in zip_names
    assert "my_package/data.json" in zip_names


def test_build_package_include(fixture_project):
    project = fixture_project("demo-package")
    project.pyproject.settings["includes"] = [
        "my_package/",
        "single_module.py",
        "data_out.json",
    ]
    project.pyproject.settings["excludes"] = ["my_package/*.json"]
    project.pyproject.write()
    actions.do_build(project)

    tar_names = get_tarball_names(project.root / "dist/demo-package-0.1.0.tar.gz")
    assert "demo-package-0.1.0/my_package/__init__.py" in tar_names
    assert "demo-package-0.1.0/my_package/data.json" not in tar_names
    assert "demo-package-0.1.0/single_module.py" in tar_names
    assert "demo-package-0.1.0/data_out.json" in tar_names

    zip_names = get_wheel_names(project.root / "dist/demo_package-0.1.0-py3-none-any.whl")
    assert "my_package/__init__.py" in zip_names
    assert "my_package/data.json" not in zip_names
    assert "single_module.py" in zip_names
    assert "data_out.json" in zip_names


def test_build_src_package_by_include(fixture_project):
    project = fixture_project("demo-src-package")
    project.pyproject.settings["includes"] = ["src/my_package"]
    project.pyproject.write()
    actions.do_build(project)

    tar_names = get_tarball_names(project.root / "dist/demo-package-0.1.0.tar.gz")
    assert "demo-package-0.1.0/src/my_package/__init__.py" in tar_names
    assert "demo-package-0.1.0/src/my_package/data.json" in tar_names

    zip_names = get_wheel_names(project.root / "dist/demo_package-0.1.0-py3-none-any.whl")
    assert "my_package/__init__.py" in zip_names
    assert "my_package/data.json" in zip_names


def test_build_with_config_settings(fixture_project):
    project = fixture_project("demo-src-package")
    actions.do_build(project, config_settings={"--plat-name": "win_amd64"})

    assert (project.root / "dist/demo_package-0.1.0-py3-none-win_amd64.whl").exists()


def test_cli_build_with_config_settings(fixture_project, invoke):
    project = fixture_project("demo-src-package")
    result = invoke(["build", "-C--plat-name=win_amd64"], obj=project)
    assert result.exit_code == 0
    assert (project.root / "dist/demo_package-0.1.0-py3-none-win_amd64.whl").exists()


@pytest.mark.network
@pytest.mark.parametrize("isolated", (True, False))
def test_build_with_no_isolation(fixture_project, invoke, isolated):
    project = fixture_project("demo-failure")
    project.pyproject.set_data({"project": {"name": "demo", "version": "0.1.0"}})
    project.pyproject.write()
    invoke(["add", "first"], obj=project)
    args = ["build"]
    if not isolated:
        args.append("--no-isolation")
    result = invoke(args, obj=project)
    assert result.exit_code == int(isolated)


def test_build_ignoring_pip_environment(fixture_project, monkeypatch):
    project = fixture_project("demo-module")
    monkeypatch.setenv("PIP_REQUIRE_VIRTUALENV", "1")
    actions.do_build(project)
