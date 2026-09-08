import platform
import sys
from pathlib import Path

import pytest
from findpython import PythonVersion as FindPythonVersion
from pbs_installer import PythonVersion

from pdm.exceptions import NoPythonVersion
from pdm.models.python import PythonInfo
from pdm.utils import parse_version


@pytest.fixture
def mock_install(mocker):
    if (arch := platform.machine().lower()) not in ("arm64", "aarch64", "amd64", "x86_64"):
        pytest.skip(f"Skipped on non-standard platform: {arch}")

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

    def get_download_link(version, *args, **kwargs):
        return f"cpython@{version}", None

    def get_version(self):
        name = self.executable.parent.name if sys.platform == "win32" else self.executable.parent.parent.name
        if "@" not in name:
            return parse_version(platform.python_version())
        return parse_version(name.split("@", 1)[1].rstrip("t"))

    def get_freethreaded(self):
        name = self.executable.parent.name if sys.platform == "win32" else self.executable.parent.parent.name
        return name.endswith("t")

    @property
    def interpreter(self):
        return self.executable

    @property
    def implementation(self):
        name = self.executable.parent.name if sys.platform == "win32" else self.executable.parent.parent.name
        if "@" not in name:
            return "cpython"
        return name.split("@", 1)[0]

    mocker.patch("pbs_installer.download", return_value="python-3.10.8.tar.gz")
    mocker.patch("pbs_installer.get_download_link", side_effect=get_download_link)
    installer = mocker.patch("pbs_installer.install_file", side_effect=install_file)
    mocker.patch("findpython.python.PythonVersion.implementation", implementation)
    mocker.patch("findpython.python.PythonVersion._get_version", get_version)
    mocker.patch("findpython.python.PythonVersion._get_freethreaded", get_freethreaded)
    mocker.patch("findpython.python.PythonVersion.interpreter", interpreter)
    mocker.patch("findpython.python.PythonVersion.architecture", mocker.PropertyMock(return_value="64bit"))
    return installer


def test_install_python(project, pdm, mock_install):
    root = Path(project.config["python.install_root"])

    pdm(["py", "install", "cpython@3.10.8", "-v"], obj=project, strict=True)
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


def test_install_python_best_match(project, pdm, mock_install, mocker):
    root = Path(project.config["python.install_root"])
    mock_best_match = mocker.patch(
        "pdm.project.core.Project.get_best_matching_cpython_version", return_value=PythonVersion("cpython", 3, 10, 8)
    )

    pdm(["py", "install"], obj=project, strict=True)
    mock_best_match.assert_called_once()
    mock_install.assert_called_once()
    assert (root / "cpython@3.10.8").exists()


def test_install_python_min_match(project, pdm, mock_install, mocker):
    root = Path(project.config["python.install_root"])
    mock_best_match = mocker.patch(
        "pdm.project.core.Project.get_best_matching_cpython_version", return_value=PythonVersion("cpython", 3, 10, 7)
    )

    pdm(["py", "install", "--min"], obj=project, strict=True)
    mock_best_match.assert_called_once_with(True)
    mock_install.assert_called_once()
    assert (root / "cpython@3.10.7").exists()


def test_use_auto_install_missing(project, pdm, mock_install, mocker):
    root = Path(project.config["python.install_root"])
    mock_find_interpreters = mocker.patch("pdm.project.Project.find_interpreters", return_value=[])
    mock_best_match = mocker.patch("pdm.project.core.Project.get_best_matching_cpython_version")

    pdm(["use", "3.10.8"], obj=project, strict=True)
    mock_install.assert_called_once()
    mock_find_interpreters.assert_called_once()
    mock_best_match.assert_not_called()
    assert (root / "cpython@3.10.8").exists()


def test_use_auto_install_pick_latest(project, pdm, mock_install, mocker):
    root = Path(project.config["python.install_root"])
    mock_find_interpreters = mocker.patch("pdm.project.Project.find_interpreters", return_value=[])
    mock_best_match = mocker.patch(
        "pdm.project.core.Project.get_best_matching_cpython_version", return_value=PythonVersion("cpython", 3, 10, 8)
    )

    pdm(["use", "-v"], obj=project, strict=True)
    mock_install.assert_called_once()
    mock_find_interpreters.assert_called_once()
    mock_best_match.assert_called_once()
    assert len(list(root.iterdir())) == 1


def test_use_no_auto_install(project, pdm, mocker):
    installer = mocker.patch("pbs_installer.install_file")
    mock_best_match = mocker.patch("pdm.project.core.Project.get_best_matching_cpython_version")

    pdm(["use", "-f"], obj=project, strict=True)
    installer.assert_not_called()
    mock_best_match.assert_not_called()


def test_use_no_managed_python(project, pdm, mocker, monkeypatch):
    monkeypatch.setenv("PDM_NO_MANAGED_PYTHON", "true")
    mock_find_interpreters = mocker.patch("pdm.project.Project.find_interpreters", return_value=[])
    mock_install = mocker.patch(
        "pdm.cli.commands.python.InstallCommand.install_python", return_value=PythonInfo.from_path(sys.executable)
    )

    result = pdm(["use", "3.10.8"], obj=project)

    assert result.exit_code != 0
    mock_find_interpreters.assert_called_once()
    mock_install.assert_not_called()


def test_use_auto_install_strategy_respects_no_managed_python(project, pdm, mocker, monkeypatch):
    monkeypatch.setenv("PDM_NO_MANAGED_PYTHON", "true")
    mock_find_interpreters = mocker.patch("pdm.project.Project.find_interpreters", return_value=[])
    mock_best_match = mocker.patch(
        "pdm.project.core.Project.get_best_matching_cpython_version", return_value=PythonVersion("cpython", 3, 10, 8)
    )
    mock_install = mocker.patch(
        "pdm.cli.commands.python.InstallCommand.install_python", return_value=PythonInfo.from_path(sys.executable)
    )

    result = pdm(["use", "--auto-install-min"], obj=project)

    assert result.exit_code != 0
    mock_find_interpreters.assert_called_once()
    mock_best_match.assert_not_called()
    mock_install.assert_not_called()


def test_no_managed_python_keeps_managed_provider_for_links(project, mocker):
    project.global_config["python.use_managed"] = False
    finder = mocker.patch("findpython.Finder")

    project._get_python_finder(search_venv=False)

    providers = finder.call_args.kwargs["selected_providers"]
    assert providers is None or "rye" in providers


def test_no_managed_python_preserves_saved_selection(project, mocker, monkeypatch):
    monkeypatch.setenv("PDM_NO_MANAGED_PYTHON", "true")
    saved_python = Path(sys.executable)
    project.global_config["python.install_root"] = str(saved_python.parent)
    project._saved_python = saved_python.as_posix()
    mocker.patch.object(project, "iter_interpreters", return_value=iter(()))

    with pytest.raises(NoPythonVersion):
        project.resolve_interpreter()

    assert project._saved_python == saved_python.as_posix()


def test_no_managed_python_finds_linked_python_by_version(project, mocker):
    project.global_config["python.use_managed"] = False
    linked_path = Path(project.config["python.install_root"]) / "cpython@3.14.0" / (
        "python.exe" if sys.platform == "win32" else "bin/python3"
    )
    linked = FindPythonVersion(
        linked_path,
        _interpreter=Path(sys.executable),
        _version=parse_version(platform.python_version()),
    )
    finder = mocker.Mock()
    finder.find_all.return_value = [linked]
    mocker.patch.object(project, "_get_python_finder", return_value=finder)

    interpreters = list(project.find_interpreters("3.14", search_venv=False))

    assert len(interpreters) == 1
    assert interpreters[0].path == linked_path
    assert interpreters[0].executable == Path(sys.executable)


def test_no_managed_python_skips_managed_path_lookup(project, mocker):
    project.global_config["python.use_managed"] = False
    wrapper = project.root.parent / "python-wrapper"
    wrapper.touch()
    managed_python = Path(project.config["python.install_root"]) / "cpython@3.14.0" / (
        "python.exe" if sys.platform == "win32" else "bin/python3"
    )
    mocker.patch("pdm.project.core.shutil.which", return_value=str(wrapper))
    mocker.patch("findpython.python.PythonVersion._get_interpreter", return_value=str(managed_python))
    finder = mocker.Mock()
    finder.find_all.return_value = []
    mocker.patch.object(project, "_get_python_finder", return_value=finder)

    interpreters = list(project.find_interpreters("python", search_venv=False))

    assert not interpreters


@pytest.mark.parametrize("shim_name", ["python3", "python"])
def test_no_managed_python_skips_managed_pyenv_shim(project, mocker, shim_name):
    project.global_config["python.use_managed"] = False
    pyenv_root = project.root.parent / "pyenv"
    pyenv_shim = pyenv_root / "shims" / (shim_name + ".bat" if sys.platform == "win32" else shim_name)
    pyenv_shim.parent.mkdir(parents=True, exist_ok=True)
    pyenv_shim.touch()
    managed_python = Path(project.config["python.install_root"]) / "cpython@3.14.0" / (
        "python.exe" if sys.platform == "win32" else "bin/python3"
    )
    mocker.patch("pdm.project.core.PYENV_ROOT", str(pyenv_root))
    mocker.patch("pdm.project.core.shutil.which", return_value=None)
    mocker.patch("findpython.python.PythonVersion._get_interpreter", return_value=str(managed_python))
    finder = mocker.Mock()
    finder.find_all.return_value = []
    mocker.patch.object(project, "_get_python_finder", return_value=finder)

    interpreters = list(project.find_interpreters(search_venv=False))

    assert all(interpreter.path != pyenv_shim for interpreter in interpreters)


def test_use_auto_install_strategy_max(project, pdm, mock_install, mocker):
    root = Path(project.config["python.install_root"])
    mock_find_interpreters = mocker.patch("pdm.project.Project.find_interpreters")
    mock_best_match = mocker.patch(
        "pdm.project.core.Project.get_best_matching_cpython_version", return_value=PythonVersion("cpython", 3, 10, 8)
    )

    pdm(["use", "--auto-install-max"], obj=project, strict=True)
    mock_install.assert_called_once()
    mock_find_interpreters.assert_not_called()
    mock_best_match.assert_called_once()
    assert len(list(root.iterdir())) == 1


def test_use_auto_install_strategy_min(project, pdm, mock_install, mocker):
    root = Path(project.config["python.install_root"])
    mock_find_interpreters = mocker.patch("pdm.project.Project.find_interpreters")
    mock_best_match = mocker.patch(
        "pdm.project.core.Project.get_best_matching_cpython_version", return_value=PythonVersion("cpython", 3, 10, 7)
    )

    pdm(["use", "--auto-install-min"], obj=project, strict=True)
    mock_install.assert_called_once()
    mock_find_interpreters.assert_not_called()
    mock_best_match.assert_called_once_with(True)
    assert len(list(root.iterdir())) == 1


def test_link_python(project, pdm):
    root = Path(project.config["python.install_root"])
    pdm(["python", "link", sys.executable], obj=project, strict=True)
    python_info = PythonInfo.from_path(sys.executable)
    link_name = f"{python_info.implementation}@{python_info.identifier}"
    assert (root / link_name).resolve() == Path(sys.prefix).resolve()

    pdm(["python", "remove", link_name], obj=project, strict=True)
    assert not (root / link_name).exists()

    pdm(["python", "link", sys.executable, "--name", "foo"], obj=project, strict=True)
    assert (root / "foo").resolve() == Path(sys.prefix).resolve()

    pdm(["python", "remove", "foo"], obj=project, strict=True)
    assert not (root / "foo").exists()


def test_link_python_invalid_interpreter(project, pdm):
    result = pdm(["python", "link", "/path/to/invalid/python"], obj=project)
    assert result.exit_code != 0
    assert "Invalid Python interpreter" in result.stderr

    root = Path(project.config["python.install_root"])
    root.mkdir(parents=True, exist_ok=True)
    root.joinpath("foo").touch()
    result = pdm(["python", "link", sys.executable, "--name", "foo"], obj=project)
    assert result.exit_code != 0
    assert "Link foo already exists" in result.stderr


def test_find_python(project, pdm, mock_install):
    pdm(["py", "install", "3.10.8"], obj=project, strict=True)
    pdm(["py", "install", "3.13.0"], obj=project, strict=True)
    pdm(["py", "install", "3.13.0t"], obj=project, strict=True)
    result = pdm(["py", "find", "3.10.8"], obj=project, strict=True)
    assert "3.10.8" in result.stdout

    result = pdm(["py", "find", "3.10.8", "--managed"], obj=project, strict=True)
    assert "3.10.8" in result.stdout

    result = pdm(["py", "find", "3.10.9"], obj=project)
    assert result.exit_code != 0

    result = pdm(["py", "find", "3.13", "--managed"], obj=project)
    assert "3.13.0t" not in result.stdout
    assert "3.13.0" in result.stdout

    result = pdm(["py", "find", "3.13t", "--managed"], obj=project)
    assert "3.13.0t" in result.stdout
