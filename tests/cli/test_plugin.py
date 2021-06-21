from unittest.mock import Mock

import pytest

from pdm.cli.commands import plugin


@pytest.fixture()
def mock_pip(monkeypatch):
    mocked = Mock()
    monkeypatch.setattr(plugin, "run_pip", mocked)
    return mocked


@pytest.fixture()
def mock_all_plugins(monkeypatch):
    monkeypatch.setattr(plugin, "_all_plugins", Mock(return_value=["demo"]))
    monkeypatch.setattr(
        plugin.importlib_metadata,
        "metadata",
        Mock(
            return_value={"Name": "demo", "Version": "0.1.0", "Summary": "Test plugin"}
        ),
    )


@pytest.mark.usefixtures("mock_all_plugins")
def test_plugin_list(invoke):
    result = invoke(["plugin", "list"])
    assert result.exit_code == 0, result.stderr
    assert "demo 0.1.0" in result.output


def test_plugin_add(invoke, mock_pip):
    result = invoke(["plugin", "add", "foo"])
    assert result.exit_code == 0, result.stderr
    mock_pip.assert_called_with(["install", "foo"])

    result = invoke(
        ["plugin", "add", "--pip-args", "--force-reinstall --upgrade", "foo"]
    )
    assert result.exit_code == 0, result.stderr
    mock_pip.assert_called_with(["install", "--force-reinstall", "--upgrade", "foo"])


@pytest.mark.usefixtures("mock_all_plugins")
def test_plugin_remove(invoke, mock_pip, monkeypatch):
    def _mock_resolve(self, packages):
        return ["demo", "pytz"] if "demo" in packages else packages

    monkeypatch.setattr(
        plugin.RemoveCommand,
        "_resolve_dependencies_to_remove",
        _mock_resolve,
    )

    result = invoke(["plugin", "remove", "foo"])
    assert result.exit_code != 0

    result = invoke(["plugin", "remove", "-y", "demo"])
    assert result.exit_code == 0, result.stderr
    mock_pip.assert_called_with(["uninstall", "-y", "demo", "pytz"])
