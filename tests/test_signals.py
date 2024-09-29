from itertools import chain
from unittest import mock

import pytest

from pdm import signals
from pdm.models.candidates import Candidate
from pdm.models.repositories import Package
from pdm.models.requirements import Requirement


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


@pytest.mark.usefixtures("working_set")
def test_lock_and_install_signals_injection_with_add(project, pdm):
    pre_lock = signals.pre_lock.connect(mock.Mock(), weak=False)
    post_lock = signals.post_lock.connect(mock.Mock(), weak=False)
    pre_install = signals.pre_install.connect(mock.Mock(), weak=False)
    post_install = signals.post_install.connect(mock.Mock(), weak=False)
    pdm(["add", "requests"], obj=project, strict=True)
    signals.pre_lock.disconnect(pre_lock)
    signals.post_lock.disconnect(post_lock)
    signals.pre_install.disconnect(pre_install)
    signals.post_install.disconnect(post_install)

    assert isinstance(pre_lock.call_args.kwargs["requirements"], list)
    assert all(isinstance(e, Requirement) for e in pre_lock.call_args.kwargs["requirements"])
    assert len(pre_lock.call_args.kwargs["requirements"]) == 1

    assert isinstance(post_lock.call_args.kwargs["resolution"], dict)
    assert all(isinstance(e, Candidate) for e in chain.from_iterable(post_lock.call_args.kwargs["resolution"].values()))
    assert len(post_lock.call_args.kwargs["resolution"]) == 5

    assert isinstance(pre_install.call_args.kwargs["packages"], list)
    assert all(isinstance(e, Package) for e in pre_install.call_args.kwargs["packages"])
    assert len(pre_install.call_args.kwargs["packages"]) == 5

    assert isinstance(post_install.call_args.kwargs["packages"], list)
    assert all(isinstance(e, Package) for e in post_install.call_args.kwargs["packages"])
    assert len(post_install.call_args.kwargs["packages"]) == 5


@pytest.mark.usefixtures("working_set")
def test_lock_and_install_signals_injection_with_install(project, pdm):
    project.add_dependencies(["requests"])

    pre_lock = signals.pre_lock.connect(mock.Mock(), weak=False)
    post_lock = signals.post_lock.connect(mock.Mock(), weak=False)
    pre_install = signals.pre_install.connect(mock.Mock(), weak=False)
    post_install = signals.post_install.connect(mock.Mock(), weak=False)
    pdm(["install"], obj=project, strict=True)
    signals.pre_lock.disconnect(pre_lock)
    signals.post_lock.disconnect(post_lock)
    signals.pre_install.disconnect(pre_install)
    signals.post_install.disconnect(post_install)

    assert isinstance(pre_lock.call_args.kwargs["requirements"], list)
    assert all(isinstance(e, Requirement) for e in pre_lock.call_args.kwargs["requirements"])
    assert len(pre_lock.call_args.kwargs["requirements"]) == 1

    assert isinstance(post_lock.call_args.kwargs["resolution"], dict)
    assert all(isinstance(e, Candidate) for e in chain.from_iterable(post_lock.call_args.kwargs["resolution"].values()))
    assert len(post_lock.call_args.kwargs["resolution"]) == 5

    assert isinstance(pre_install.call_args.kwargs["packages"], list)
    assert all(isinstance(e, Package) for e in pre_install.call_args.kwargs["packages"])
    assert len(pre_install.call_args.kwargs["packages"]) == 5

    assert isinstance(post_install.call_args.kwargs["packages"], list)
    assert all(isinstance(e, Package) for e in post_install.call_args.kwargs["packages"])
    assert len(post_install.call_args.kwargs["packages"]) == 5


@pytest.mark.usefixtures("working_set")
def test_lock_signals_injection_with_update(project, pdm):
    project.add_dependencies(["requests"])

    pre_lock = signals.pre_lock.connect(mock.Mock(), weak=False)
    post_lock = signals.post_lock.connect(mock.Mock(), weak=False)
    pdm(["update"], obj=project, strict=True)
    signals.pre_lock.disconnect(pre_lock)
    signals.post_lock.disconnect(post_lock)

    assert isinstance(pre_lock.call_args.kwargs["requirements"], list)
    assert all(isinstance(e, Requirement) for e in pre_lock.call_args.kwargs["requirements"])
    assert len(pre_lock.call_args.kwargs["requirements"]) == 1

    assert isinstance(post_lock.call_args.kwargs["resolution"], dict)
    assert all(isinstance(e, Candidate) for e in chain.from_iterable(post_lock.call_args.kwargs["resolution"].values()))
    assert len(post_lock.call_args.kwargs["resolution"]) == 5
