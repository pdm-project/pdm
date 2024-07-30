from types import SimpleNamespace
from unittest.mock import ANY

import pytest

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
    mocker.patch("pdm.cli.commands.self_cmd.WorkingSet", return_value=DISTRIBUTIONS)


@pytest.fixture()
def mock_latest_pdm_version(mocker):
    return mocker.patch(
        "pdm.cli.commands.self_cmd.get_latest_pdm_version_from_pypi",
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
        (["self", "update"], ["install", "--upgrade", "pdm==99.0.0"]),
        (["self", "update", "--pre"], ["install", "--upgrade", "pdm==99.0.1b1"]),
        (
            ["self", "update", "--head"],
            ["install", "--upgrade", f"pdm @ git+{self_cmd.PDM_REPO}@main"],
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
