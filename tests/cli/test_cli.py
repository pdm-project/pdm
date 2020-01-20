import functools

import pytest
from click.testing import CliRunner

from pdm.cli import actions, commands


@pytest.fixture()
def invoke():
    runner = CliRunner()
    return functools.partial(runner.invoke, commands.cli)


def test_lock_command(project, invoke, mocker):
    m = mocker.patch.object(actions, "do_lock")
    invoke(["lock"])
    m.assert_called_once()
