import sys
from pathlib import Path

import pytest
from packaging.version import Version


@pytest.fixture
def mock_install(mocker):
    def install_file(
        filename,
        destination,
        original_filename=None,
        build_dir=False,
    ) -> None:
        if sys.platform == "win32":
            Path(destination, "python.exe").touch()
        else:
            Path(destination, "bin").mkdir(parents=True, exist_ok=True)
            Path(destination, "bin", "python3").touch()

    def get_version(self):
        if sys.platform == "win32":
            return Version(self.executable.parent.name.split("-", 1)[1])
        else:
            return Version(self.executable.parent.parent.name.split("@", 1)[1])

    @property
    def interpreter(self):
        return self.executable

    @property
    def implementation(self):
        if sys.platform == "win32":
            return self.executable.parent.name.split("-", 1)[0]
        else:
            return self.executable.parent.parent.name.split("@", 1)[0]

    mocker.patch("pbs_installer.download", return_value="python-3.10.8.tar.gz")
    installer = mocker.patch("pbs_installer.install_file", side_effect=install_file)
    mocker.patch("findpython.python.PythonVersion.implementation", implementation)
    mocker.patch("findpython.python.PythonVersion._get_version", get_version)
    mocker.patch("findpython.python.PythonVersion.interpreter", interpreter)
    return installer


def test_install_python(project, pdm, mock_install):
    root = Path(project.config["python.install_root"])

    pdm(["py", "install", "cpython@3.10.8"], obj=project, strict=True)
    mock_install.assert_called_once()
    assert (root / "cpython@3.10.8").exists()

    result = pdm(["py", "list"], obj=project, strict=True)
    assert result.stdout.splitlines()[0].startswith("cpython@3.10.8")

    result = pdm(["py", "remove", "3.11.1"], obj=project)
    assert result.exit_code != 0
    pdm(["py", "remove", "cpython@3.10.8"], obj=project, strict=True)
    assert not (root / "cpython@3.10.8").exists()

    result = pdm(["py", "install", "--list"], obj=project, strict=True)
    assert len(result.stdout.splitlines()) > 0


def test_use_auto_install_missing(project, pdm, mock_install, mocker):
    root = Path(project.config["python.install_root"])
    mocker.patch("pdm.project.Project.find_interpreters", return_value=[])

    pdm(["use", "3.10.8"], obj=project, strict=True)
    mock_install.assert_called_once()
    assert (root / "cpython@3.10.8").exists()


def test_use_no_auto_install(project, pdm, mocker):
    installer = mocker.patch("pbs_installer.install_file")

    pdm(["use", "-f", "-v"], obj=project, strict=True)
    installer.assert_not_called()
