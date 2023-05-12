import sys
from unittest import mock

import pytest

from pdm.cli.commands.base import BaseCommand
from pdm.compat import importlib_metadata
from pdm.project.config import ConfigItem
from pdm.utils import cd


class HelloCommand(BaseCommand):
    def add_arguments(self, parser) -> None:
        parser.add_argument("-n", "--name", help="The person's name")

    def handle(self, project, options) -> None:
        greeting = "Hello world"
        if options.name:
            greeting = f"Hello, {options.name}"
        print(greeting)


def new_command(core):
    core.register_command(HelloCommand, "hello")


def replace_command(core):
    core.register_command(HelloCommand, "info")


def add_new_config(core):
    core.add_config("foo", ConfigItem("Test config", "bar"))


def make_entry_point(plugin):
    ret = mock.Mock()
    ret.load.return_value = plugin
    return ret


def test_plugin_new_command(pdm, mocker, project, core):
    mocker.patch.object(
        importlib_metadata,
        "entry_points",
        return_value=[make_entry_point(new_command)],
    )
    core.init_parser()
    core.load_plugins()
    result = pdm(["--help"], obj=project)
    assert "hello" in result.output

    result = pdm(["hello"], obj=project)
    assert result.output.strip() == "Hello world"

    result = pdm(["hello", "-n", "Frost"], obj=project)
    assert result.output.strip() == "Hello, Frost"


def test_plugin_replace_command(pdm, mocker, project, core):
    mocker.patch.object(
        importlib_metadata,
        "entry_points",
        return_value=[make_entry_point(replace_command)],
    )
    core.init_parser()
    core.load_plugins()

    result = pdm(["info"], obj=project)
    assert result.output.strip() == "Hello world"

    result = pdm(["info", "-n", "Frost"], obj=project)
    assert result.output.strip() == "Hello, Frost"


def test_load_multiple_plugings(pdm, mocker, core):
    mocker.patch.object(
        importlib_metadata,
        "entry_points",
        return_value=[make_entry_point(new_command), make_entry_point(add_new_config)],
    )
    core.init_parser()
    core.load_plugins()

    result = pdm(["hello"])
    assert result.output.strip() == "Hello world", result.outputs

    result = pdm(["config", "foo"])
    assert result.output.strip() == "bar"


def test_old_entry_point_compatibility(pdm, mocker, core):
    def get_entry_points(group):
        if group == "pdm":
            return [make_entry_point(new_command)]
        if group == "pdm.plugin":
            return [make_entry_point(add_new_config)]
        return []

    mocker.patch.object(importlib_metadata, "entry_points", side_effect=get_entry_points)
    core.init_parser()
    core.load_plugins()

    result = pdm(["hello"])
    assert result.output.strip() == "Hello world"

    result = pdm(["config", "foo"])
    assert result.output.strip() == "bar"


@pytest.mark.usefixtures("local_finder")
def test_project_plugin_library(pdm, project, core, monkeypatch):
    monkeypatch.setattr(sys, "path", sys.path[:])
    project.pyproject.settings["plugins"] = ["pdm-hello"]
    pdm(["install", "--plugins"], obj=project, strict=True)
    assert project.root.joinpath(".pdm-plugins").exists()
    assert "pdm-hello" not in project.environment.get_working_set()
    with cd(project.root):
        core.load_plugins()
        result = pdm(["hello", "Frost"], strict=True)
    assert result.stdout.strip() == "Hello, Frost!"
