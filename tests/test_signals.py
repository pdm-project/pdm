from unittest import mock

import pytest

from pdm import signals


def test_post_init_signal(project_no_init, pdm):
    mock_handler = mock.Mock()
    with signals.post_init.connected_to(mock_handler):
        result = pdm(["init"], input="\n\n\n\n\n\n\n\n", obj=project_no_init)
        assert result.exit_code == 0
    mock_handler.assert_called_once_with(project_no_init, hooks=mock.ANY)


@pytest.mark.usefixtures("working_set")
def test_post_lock_and_install_signals(project, pdm):
    pre_lock = signals.pre_lock.connect(mock.Mock(), weak=False)
    post_lock = signals.post_lock.connect(mock.Mock(), weak=False)
    pre_install = signals.pre_install.connect(mock.Mock(), weak=False)
    post_install = signals.post_install.connect(mock.Mock(), weak=False)
    pdm(["add", "requests"], obj=project, strict=True)
    signals.pre_lock.disconnect(pre_lock)
    signals.post_lock.disconnect(post_lock)
    signals.pre_install.disconnect(pre_install)
    signals.post_install.disconnect(post_install)
    for mocker in (pre_lock, post_lock, pre_install, post_install):
        mocker.assert_called_once()
