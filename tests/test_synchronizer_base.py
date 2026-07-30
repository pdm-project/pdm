from __future__ import annotations

import dataclasses

import pytest

from pdm.exceptions import BuildError
from pdm.installers.base import BaseSynchronizer, editables_candidate
from pdm.models.candidates import Candidate
from pdm.models.requirements import parse_requirement


def make_synchronizer(mocker):
    synchronizer = object.__new__(BaseSynchronizer)
    synchronizer.environment = mocker.Mock()
    synchronizer.environment.project.backend.expand_line.side_effect = lambda value: value
    synchronizer.reinstall = False
    synchronizer.no_editable = False
    synchronizer.install_self = False
    return synchronizer


@pytest.mark.parametrize("has_match", [False, True])
def test_editables_candidate(mocker, has_match):
    best = mocker.Mock() if has_match else None
    finder = mocker.MagicMock()
    finder.find_best_match.return_value.best = best
    environment = mocker.MagicMock()
    environment.get_finder.return_value.__enter__.return_value = finder
    from_installation_candidate = mocker.patch(
        "pdm.installers.base.Candidate.from_installation_candidate",
    )

    result = editables_candidate(environment)

    if has_match:
        assert result is from_installation_candidate.return_value
        from_installation_candidate.assert_called_once()
    else:
        assert result is None


@pytest.mark.parametrize(
    ("install_self", "has_editables", "requires", "build_error", "expected"),
    [
        (False, False, ["editables"], False, False),
        (True, True, ["editables"], False, False),
        (True, False, ["other"], False, False),
        (True, False, ["editables>=0.5"], False, True),
        (True, False, [], True, False),
    ],
)
def test_should_install_editables(mocker, install_self, has_editables, requires, build_error, expected):
    synchronizer = make_synchronizer(mocker)
    synchronizer.install_self = install_self
    synchronizer.requested_candidates = {"editables": mocker.Mock()} if has_editables else {}
    prepared = mocker.Mock()
    prepared.metadata.requires = requires
    candidate = mocker.Mock()
    candidate.prepare.return_value = prepared
    if build_error:
        candidate.prepare.side_effect = BuildError("failed")
    synchronizer.__dict__["self_candidate"] = candidate

    assert synchronizer.should_install_editables() is expected


def test_candidates_marks_requested_and_converts_editable(mocker):
    synchronizer = make_synchronizer(mocker)
    editable_req = dataclasses.replace(parse_requirement("demo"), editable=True)
    editable = Candidate(editable_req, name="demo", version="1.0")
    regular = Candidate(parse_requirement("regular"), name="regular", version="2.0")
    synchronizer.requested_candidates = {"demo": editable, "regular": regular}
    synchronizer.requirements = [parse_requirement("regular")]
    synchronizer.no_editable = ["demo"]

    result = synchronizer.candidates

    assert result["demo"].req.editable is False
    assert result["regular"].requested is True


def test_candidates_adds_editables_dependency(mocker):
    synchronizer = make_synchronizer(mocker)
    synchronizer.requested_candidates = {}
    synchronizer.requirements = []
    synchronizer.environment.project.all_dependencies = {}
    synchronizer.no_editable = False
    mocker.patch.object(synchronizer, "should_install_editables", return_value=True)
    candidate = mocker.patch("pdm.installers.base.editables_candidate").return_value

    assert synchronizer.candidates == {"editables": candidate}


def test_should_update_immediate_cases(mocker):
    synchronizer = make_synchronizer(mocker)
    dist = mocker.Mock()
    candidate = mocker.Mock()
    candidate.req.editable = False

    synchronizer.reinstall = True
    assert synchronizer._should_update(dist, candidate)
    synchronizer.reinstall = False
    candidate.req.editable = True
    assert synchronizer._should_update(dist, candidate)
    candidate.req.editable = False
    mocker.patch("pdm.installers.base.is_editable", return_value=True)
    assert not synchronizer._should_update(dist, candidate)
    synchronizer.no_editable = True
    assert synchronizer._should_update(dist, candidate)


@pytest.mark.parametrize(
    ("direct_url", "hashes", "expected"),
    [
        (None, [], False),
        ('{"url": "x"}', [], False),
        ('{"archive_info": {"hash": "sha256=abc"}}', [{"hash": "sha256:abc"}], False),
        ('{"archive_info": {"hash": "sha256=abc"}}', [{"hash": "sha256:def"}], True),
    ],
)
def test_should_update_archive_requirement(mocker, direct_url, hashes, expected):
    synchronizer = make_synchronizer(mocker)
    mocker.patch("pdm.installers.base.is_editable", return_value=False)
    dist = mocker.Mock()
    dist.read_text.return_value = direct_url
    installed_req = parse_requirement("demo @ https://example.org/demo.whl")
    mocker.patch("pdm.installers.base.Requirement.from_dist", return_value=installed_req)
    candidate = mocker.Mock()
    candidate.req.is_named = False
    candidate.req.editable = False
    candidate.link.url_without_fragment = "https://example.org/demo.whl"
    candidate.hashes = hashes

    assert synchronizer._should_update(dist, candidate) is expected


def test_should_update_changed_url_and_local_directory(mocker):
    synchronizer = make_synchronizer(mocker)
    mocker.patch("pdm.installers.base.is_editable", return_value=False)
    candidate = mocker.Mock()
    candidate.req.is_named = False
    candidate.req.editable = False
    candidate.link.url_without_fragment = "https://example.org/new.whl"
    installed_req = mocker.Mock()
    installed_req.is_local_dir = False
    installed_req.get_full_url.return_value = "https://example.org/old.whl"
    mocker.patch("pdm.installers.base.Requirement.from_dist", return_value=installed_req)
    mocker.patch("pdm.installers.base.FileRequirement", type(installed_req))

    assert synchronizer._should_update(mocker.Mock(), candidate)
    installed_req.is_local_dir = True
    assert synchronizer._should_update(mocker.Mock(), candidate)


def test_should_update_unknown_direct_requirement(mocker):
    synchronizer = make_synchronizer(mocker)
    mocker.patch("pdm.installers.base.is_editable", return_value=False)
    mocker.patch("pdm.installers.base.Requirement.from_dist", return_value=mocker.Mock())
    candidate = mocker.Mock()
    candidate.req.is_named = False
    candidate.req.editable = False

    assert synchronizer._should_update(mocker.Mock(), candidate)


def test_self_key_preserves_empty_project_name(mocker):
    synchronizer = make_synchronizer(mocker)
    synchronizer.install_self = True
    synchronizer.environment.project.name = ""

    assert synchronizer.self_key == ""


def test_synchronize_applies_all_operations(mocker):
    synchronizer = make_synchronizer(mocker)
    synchronizer.compare_with_working_set = mocker.Mock(return_value=(["add"], ["update"], ["remove"]))
    add_candidate = mocker.Mock(version="1")
    update_candidate = mocker.Mock(version="2")
    synchronizer.__dict__["candidates"] = {"add": add_candidate, "update": update_candidate}
    update_dist = mocker.Mock(version="1")
    remove_dist = mocker.Mock(version="3")
    synchronizer.working_set = {"update": update_dist, "remove": remove_dist}
    manager = mocker.Mock()
    synchronizer.get_manager = mocker.Mock(return_value=manager)

    synchronizer.synchronize()

    manager.install.assert_called_once_with(add_candidate)
    manager.overwrite.assert_called_once_with(update_dist, update_candidate)
    manager.uninstall.assert_called_once_with(remove_dist)


@pytest.mark.parametrize("already_installed", [False, True])
def test_synchronize_installs_self(mocker, already_installed):
    synchronizer = make_synchronizer(mocker)
    synchronizer.install_self = True
    synchronizer.no_editable = False
    synchronizer.compare_with_working_set = mocker.Mock(return_value=([], [], []))
    synchronizer.__dict__["self_candidate"] = mocker.sentinel.self_candidate
    synchronizer.environment.project.name = "Demo"
    dist = mocker.sentinel.dist
    synchronizer.working_set = {"demo": dist} if already_installed else {}
    manager = mocker.Mock()
    synchronizer.get_manager = mocker.Mock(return_value=manager)

    synchronizer.synchronize()

    if already_installed:
        manager.overwrite.assert_called_once_with(dist, mocker.sentinel.self_candidate)
    else:
        manager.install.assert_called_once_with(mocker.sentinel.self_candidate)
