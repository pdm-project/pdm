from argparse import ArgumentParser
from typing import Any, Callable, Optional
from unittest import mock

from pip._vendor import pkg_resources
from pytest_mock.plugin import MockerFixture

from pdm.cli.commands.base import BaseCommand
from pdm.core import Core
from pdm.project.config import ConfigItem
from pdm.project.core import Project
from tests.conftest import TestProject


class HelloCommand(BaseCommand):
    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("-n", "--name", help="The person's name")

    def handle(self, project: Project, options: Optional[Any]) -> None:
        greeting = "Hello world"
        if options.name:
            greeting = f"Hello, {options.name}"
        print(greeting)


def new_command(core: Core) -> None:
    core.register_command(HelloCommand, "hello")


def replace_command(core: Core) -> None:
    core.register_command(HelloCommand, "info")


def add_new_config(core: Core) -> None:
    core.add_config("foo", ConfigItem("Test config", "bar"))


def make_entry_point(plugin: Callable[[Core], Any]) -> Any:
    ret = mock.Mock()
    ret.load.return_value = plugin
    return ret


def test_plugin_new_command(
    invoke: Callable, mocker: MockerFixture, project: TestProject
) -> None:
    mocker.patch.object(
        pkg_resources, "iter_entry_points", return_value=[make_entry_point(new_command)]
    )
    result = invoke(["--help"], obj=project)
    assert "hello" in result.output

    result = invoke(["hello"], obj=project)
    assert result.output.strip() == "Hello world"

    result = invoke(["hello", "-n", "Frost"], obj=project)
    assert result.output.strip() == "Hello, Frost"


def test_plugin_replace_command(
    invoke: Callable, mocker: MockerFixture, project: TestProject
) -> None:
    mocker.patch.object(
        pkg_resources,
        "iter_entry_points",
        return_value=[make_entry_point(replace_command)],
    )

    result = invoke(["info"], obj=project)
    assert result.output.strip() == "Hello world"

    result = invoke(["info", "-n", "Frost"], obj=project)
    assert result.output.strip() == "Hello, Frost"


def test_load_multiple_plugings(
    invoke: Callable, mocker: MockerFixture, project: TestProject
) -> None:
    mocker.patch.object(
        pkg_resources,
        "iter_entry_points",
        return_value=[make_entry_point(new_command), make_entry_point(add_new_config)],
    )

    result = invoke(["hello"])
    assert result.output.strip() == "Hello world"

    result = invoke(["config", "foo"])
    assert result.output.strip() == "bar"
