from types import SimpleNamespace
from unittest.mock import ANY

import pytest

from pdm import termui
from pdm.cli.commands import self_cmd


def mock_distribution(metadata, entry_points=()):
    entry_points = (SimpleNamespace(group=ep) for ep in entry_points)
    return SimpleNamespace(metadata=metadata, entry_points=entry_points)


DISTRIBUTIONS = {
    "foo": mock_distribution({"Name": "foo", "Version": "1.0.0", "Summary": "Foo package"}, ["pdm.plugin"]),
    "bar": mock_distribution({"Name": "bar", "Version": "2.0.0", "Summary": "Bar package"}, ["pdm"]),
    "baz": mock_distribution({"Name": "baz", "Version": "3.0.0", "Summary": "Baz package"}),
}


@pytest.fixture()
def mock_pip(mocker):
    mocked = mocker.patch("pdm.cli.commands.self_cmd.run_pip")
    return mocked


@pytest.fixture()
def mock_all_distributions(mocker):
    mocker.patch("pdm.models.working_set.WorkingSet", return_value=DISTRIBUTIONS)


@pytest.fixture()
def mock_latest_pdm_version(mocker):
    return mocker.patch(
        "pdm.cli.actions.get_latest_pdm_version_from_pypi",
    )


@pytest.mark.usefixtures("mock_all_distributions")
def test_self_list(pdm):
    result = pdm(["self", "list"])
    assert result.exit_code == 0, result.stderr
    packages = [line.split()[0] for line in result.stdout.splitlines()]
    assert packages == ["bar", "baz", "foo"]


@pytest.mark.usefixtures("mock_all_distributions")
def test_self_list_plugins(pdm):
    result = pdm(["self", "list", "--plugins"])
    assert result.exit_code == 0, result.stderr
    packages = [line.split()[0] for line in result.stdout.splitlines()]
    assert packages == ["bar", "foo"]


def test_self_add(pdm, mock_pip):
    result = pdm(["self", "add", "foo"])
    assert result.exit_code == 0, result.stderr
    mock_pip.assert_called_with(ANY, ["install", "foo"])

    result = pdm(["self", "add", "--pip-args", "--force-reinstall --upgrade", "foo"])
    assert result.exit_code == 0, result.stderr
    mock_pip.assert_called_with(ANY, ["install", "--force-reinstall", "--upgrade", "foo"])


def test_self_remove(pdm, mock_pip, mocker, monkeypatch):
    from rich import get_console

    console = get_console()

    def _mock_resolve(packages):
        return ["demo", "pytz"] if "demo" in packages else packages

    mocker.patch.object(
        self_cmd.RemoveCommand,
        "_resolve_dependencies_to_remove",
        side_effect=_mock_resolve,
    )
    mocker.patch.object(console, "is_interactive", True)

    result = pdm(["self", "remove", "foo"])
    assert result.exit_code != 0

    result = pdm(["self", "remove", "-y", "demo"])
    assert result.exit_code == 0, result.stderr
    mock_pip.assert_called_with(ANY, ["uninstall", "-y", "demo", "pytz"])

    with monkeypatch.context() as m:
        m.setenv("PDM_NON_INTERACTIVE", "1")
        result = pdm(["self", "remove", "demo"])
        assert result.exit_code == 0, result.stderr
        mock_pip.assert_called_with(ANY, ["uninstall", "-y", "demo", "pytz"])

    result = pdm(["-n", "self", "remove", "demo"])
    assert result.exit_code == 0, result.stderr
    mock_pip.assert_called_with(ANY, ["uninstall", "-y", "demo", "pytz"])


@pytest.mark.parametrize(
    "args,expected",
    [
        (["self", "update"], ["install", "--upgrade", "--upgrade-strategy", "eager", "pdm[locked]==99.0.0"]),
        (["self", "update", "--pre"], ["install", "--upgrade", "--upgrade-strategy", "eager", "pdm[locked]==99.0.1b1"]),
        (
            ["self", "update", "--head"],
            ["install", "--upgrade", "--upgrade-strategy", "eager", f"pdm[locked] @ git+{self_cmd.PDM_REPO}@main"],
        ),
    ],
)
def test_self_update(pdm, mock_pip, mock_latest_pdm_version, args, expected):
    def mocked_latest_version(project, pre):
        return "99.0.1b1" if pre else "99.0.0"

    mock_latest_pdm_version.side_effect = mocked_latest_version

    result = pdm(args)
    assert result.exit_code == 0, result.stderr
    mock_pip.assert_called_with(ANY, expected)


def test_self_update_already_latest(pdm, mock_pip, mock_latest_pdm_version):
    mock_latest_pdm_version.return_value = "0.0.0"

    result = pdm(["self", "update"])
    assert result.exit_code == 0, result.stderr
    assert "Already up-to-date" in result.stdout
    mock_pip.assert_not_called()


@pytest.mark.parametrize("use_uv", [False, True])
def test_run_pip_builds_command(project, mocker, use_uv):
    project.project_config["use_uv"] = use_uv
    project.core.uv_cmd = ["uv"]
    completed = mocker.patch("pdm.cli.commands.self_cmd.subprocess.run").return_value
    if not use_uv:
        environment = mocker.Mock(pip_command=["python", "-m", "pip"])
        bare_environment = mocker.patch("pdm.environments.BareEnvironment", return_value=environment)

    result = self_cmd.run_pip(project, ["install", "--upgrade-strategy", "eager", "demo"])

    assert result is completed
    if use_uv:
        expected = ["uv", "pip", "install", "demo", "--python", self_cmd.sys.executable]
    else:
        expected = ["python", "-m", "pip", "install", "--upgrade-strategy", "eager", "demo"]
        bare_environment.assert_called_once_with(project)
        assert project.environment is environment
    self_cmd.subprocess.run.assert_called_once_with(
        expected,
        stdout=self_cmd.subprocess.PIPE,
        stderr=self_cmd.subprocess.STDOUT,
        check=True,
        text=True,
    )


def test_self_list_without_plugins_exits(pdm, mocker):
    mocker.patch("pdm.cli.commands.self_cmd.list_distributions", return_value=[])

    result = pdm(["self", "list", "--plugins"])

    assert result.exit_code == 1
    assert "No plugin is installed" in result.stderr


@pytest.mark.parametrize("command", ["add", "remove", "update"])
def test_self_commands_report_pip_failure(pdm, mocker, command):
    error = self_cmd.subprocess.CalledProcessError(1, ["pip"], output="pip failed")
    mocker.patch("pdm.cli.commands.self_cmd.run_pip", side_effect=error)
    if command == "remove":
        mocker.patch.object(self_cmd.RemoveCommand, "_resolve_dependencies_to_remove", return_value=["demo"])
        args = ["self", command, "-y", "demo"]
    elif command == "update":
        mocker.patch("pdm.cli.actions.get_latest_pdm_version_from_pypi", return_value="99.0.0")
        args = ["self", command]
    else:
        args = ["self", command, "demo"]

    result = pdm(args)

    assert result.exit_code == 1
    assert "pip failed" in result.stderr


def test_self_remove_resolves_orphan_dependencies(mocker):
    root = mock_distribution({"Name": "root", "Version": "1.0"}, ())
    root.requires = ["dep", "pdm"]
    root.version = "1.0"
    dep = mock_distribution({"Name": "dep", "Version": "1.0"}, ())
    dep.requires = []
    dep.version = "1.0"
    pdm_dist = mock_distribution({"Name": "pdm", "Version": "1.0"}, ())
    pdm_dist.requires = []
    pdm_dist.version = "1.0"
    working_set = {"root": root, "dep": dep, "pdm": pdm_dist}
    mocker.patch("pdm.models.working_set.WorkingSet", return_value=working_set)

    result = self_cmd.RemoveCommand()._resolve_dependencies_to_remove(["root", "missing"])

    assert result == ["dep", "root"]


def test_self_remove_can_be_cancelled(pdm, mocker):
    mocker.patch.object(self_cmd.RemoveCommand, "_resolve_dependencies_to_remove", return_value=["demo"])
    mocker.patch.object(termui, "confirm", return_value=False)
    run_pip = mocker.patch("pdm.cli.commands.self_cmd.run_pip")

    result = pdm(["self", "remove", "demo"])

    assert result.exit_code == 0
    run_pip.assert_not_called()


def test_self_remove_without_matching_packages(pdm, mocker):
    mocker.patch.object(self_cmd.RemoveCommand, "_resolve_dependencies_to_remove", return_value=[])

    result = pdm(["self", "remove", "missing"])

    assert result.exit_code == 1
    assert "No package to remove" in result.stderr


def test_self_command_without_subcommand_shows_help(pdm):
    result = pdm(["self"])

    assert result.exit_code == 0
    assert "Manage the PDM program itself" in result.stdout


def test_self_zipapp_only_registers_list_command(mocker):
    parser = self_cmd.argparse.ArgumentParser()
    mocker.patch("pdm.cli.commands.self_cmd.is_in_zipapp", return_value=True)
    list_register = mocker.patch.object(self_cmd.ListCommand, "register_to")
    add_register = mocker.patch.object(self_cmd.AddCommand, "register_to")

    self_cmd.Command().add_arguments(parser)

    list_register.assert_called_once()
    add_register.assert_not_called()


def test_run_pip_uv_without_upgrade_strategy(project, mocker):
    project.project_config["use_uv"] = True
    project.core.uv_cmd = ["uv"]
    run = mocker.patch("pdm.cli.commands.self_cmd.subprocess.run")

    self_cmd.run_pip(project, ["install", "demo"])

    assert run.call_args.args[0] == ["uv", "pip", "install", "demo", "--python", self_cmd.sys.executable]
