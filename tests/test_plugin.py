from unittest import mock

from pip._vendor import pkg_resources

from pdm.cli.commands.base import BaseCommand
from pdm.project.config import ConfigItem


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


def test_plugin_new_command(invoke, mocker, project):
    mocker.patch.object(
        pkg_resources, "iter_entry_points", return_value=[make_entry_point(new_command)]
    )
    result = invoke(["--help"], obj=project)
    assert "hello" in result.output

    result = invoke(["hello"], obj=project)
    assert result.output.strip() == "Hello world"

    result = invoke(["hello", "-n", "Frost"], obj=project)
    assert result.output.strip() == "Hello, Frost"


def test_plugin_replace_command(invoke, mocker, project):
    mocker.patch.object(
        pkg_resources,
        "iter_entry_points",
        return_value=[make_entry_point(replace_command)],
    )

    result = invoke(["info"], obj=project)
    assert result.output.strip() == "Hello world"

    result = invoke(["info", "-n", "Frost"], obj=project)
    assert result.output.strip() == "Hello, Frost"


def test_load_multiple_plugings(invoke, mocker, project):
    mocker.patch.object(
        pkg_resources,
        "iter_entry_points",
        return_value=[make_entry_point(new_command), make_entry_point(add_new_config)],
    )

    result = invoke(["hello"])
    assert result.output.strip() == "Hello world"

    result = invoke(["config", "foo"])
    assert result.output.strip() == "bar"
