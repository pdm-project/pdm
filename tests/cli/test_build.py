import tarfile
import zipfile

from distlib.wheel import Wheel

from pdm.cli import actions


def get_tarball_names(path):
    with tarfile.open(path, "r:gz") as tar:
        return tar.getnames()


def get_wheel_names(path):
    with zipfile.ZipFile(path) as zf:
        return zf.namelist()


def test_build_single_module(fixture_project):
    project = fixture_project("demo-module")
    assert project.meta.version == "0.1.0"

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

    zip_names = get_wheel_names(
        project.root / "dist/demo_module-0.1.0-py3-none-any.whl"
    )
    for name in ["foo_module.py", "bar_module.py"]:
        assert name in zip_names

    for name in ("pyproject.toml", "LICENSE"):
        assert name not in zip_names

    assert Wheel(
        (project.root / "dist/demo_module-0.1.0-py3-none-any.whl").as_posix()
    ).metadata


def test_build_single_module_with_readme(fixture_project):
    project = fixture_project("demo-module")
    project.meta["readme"] = "README.md"
    project.write_pyproject()
    actions.do_build(project)
    assert "demo-module-0.1.0/README.md" in get_tarball_names(
        project.root / "dist/demo-module-0.1.0.tar.gz"
    )


def test_build_package(fixture_project):
    project = fixture_project("demo-package")
    actions.do_build(project)

    tar_names = get_tarball_names(project.root / "dist/demo-package-0.1.0.tar.gz")
    assert "demo-package-0.1.0/my_package/__init__.py" in tar_names
    assert "demo-package-0.1.0/my_package/data.json" in tar_names
    assert "demo-package-0.1.0/single_module.py" not in tar_names
    assert "demo-package-0.1.0/data_out.json" not in tar_names

    zip_names = get_wheel_names(
        project.root / "dist/demo_package-0.1.0-py3-none-any.whl"
    )
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

    zip_names = get_wheel_names(
        project.root / "dist/demo_package-0.1.0-py3-none-any.whl"
    )
    assert "my_package/__init__.py" in zip_names
    assert "my_package/data.json" in zip_names


def test_build_package_include(fixture_project):
    project = fixture_project("demo-package")
    project.tool_settings["includes"] = [
        "my_package/",
        "single_module.py",
        "data_out.json",
    ]
    project.tool_settings["excludes"] = ["my_package/*.json"]
    project.write_pyproject()
    actions.do_build(project)

    tar_names = get_tarball_names(project.root / "dist/demo-package-0.1.0.tar.gz")
    assert "demo-package-0.1.0/my_package/__init__.py" in tar_names
    assert "demo-package-0.1.0/my_package/data.json" not in tar_names
    assert "demo-package-0.1.0/single_module.py" in tar_names
    assert "demo-package-0.1.0/data_out.json" in tar_names

    zip_names = get_wheel_names(
        project.root / "dist/demo_package-0.1.0-py3-none-any.whl"
    )
    assert "my_package/__init__.py" in zip_names
    assert "my_package/data.json" not in zip_names
    assert "single_module.py" in zip_names
    assert "data_out.json" in zip_names


def test_build_src_package_by_include(fixture_project):
    project = fixture_project("demo-src-package")
    project.includes = ["src/my_package"]
    project.write_pyproject()
    actions.do_build(project)

    tar_names = get_tarball_names(project.root / "dist/demo-package-0.1.0.tar.gz")
    assert "demo-package-0.1.0/src/my_package/__init__.py" in tar_names
    assert "demo-package-0.1.0/src/my_package/data.json" in tar_names

    zip_names = get_wheel_names(
        project.root / "dist/demo_package-0.1.0-py3-none-any.whl"
    )
    assert "my_package/__init__.py" in zip_names
    assert "my_package/data.json" in zip_names


def test_build_legacy_package(fixture_project, invoke):
    project = fixture_project("demo-legacy")
    result = invoke(["build"], obj=project)
    assert project.meta.name == "demo-module"
    assert result.exit_code == 0
    assert "demo-module-0.1.0/foo_module.py" in get_tarball_names(
        project.root / "dist/demo-module-0.1.0.tar.gz"
    )
