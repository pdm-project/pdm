from __future__ import annotations

import pytest

from pdm.exceptions import CandidateNotFound
from pdm.models.candidates import Candidate
from pdm.models.markers import EnvSpec
from pdm.models.repositories.lock import LockedRepository, Package
from pdm.models.requirements import parse_requirement
from pdm.models.specifiers import PySpecSet


def make_repository(mocker):
    repository = object.__new__(LockedRepository)
    repository.packages = {}
    repository.targets = []
    repository.env_spec = EnvSpec.current()
    repository.environment = mocker.Mock()
    repository.environment.project.backend.expand_line.side_effect = lambda value: value
    repository.environment.project.python_requires = PySpecSet(">=3.9")
    repository.environment.python_requires = PySpecSet(">=3.9")
    return repository


def make_candidate(requirement="demo", version="1.0"):
    return Candidate(parse_requirement(requirement), name="demo", version=version)


def test_get_dependencies_populates_candidate_metadata(mocker):
    repository = make_repository(mocker)
    locked = make_candidate(version="2.0")
    locked.requires_python = ">=3.9"
    key = ("demo", "2.0", None, False)
    repository.packages[key] = Package(locked, ["dep>=1"], "summary")
    candidate = make_candidate(version="2.0")
    candidate.name = None
    candidate.version = None
    candidate.requires_python = ""
    mocker.patch.object(repository, "_identify_candidate", return_value=key)

    metadata = repository._get_dependencies_from_lockfile(candidate)

    assert [requirement.as_line() for requirement in metadata.dependencies] == ["dep>=1"]
    assert metadata.requires_python == ">=3.9"
    assert metadata.summary == "summary"
    assert candidate.name == "demo"
    assert candidate.version == "2.0"


def test_get_dependencies_rejects_missing_dependency_data(mocker):
    repository = make_repository(mocker)
    candidate = make_candidate()
    key = repository._identify_candidate(candidate)
    repository.packages[key] = Package(candidate, None)

    with pytest.raises(CandidateNotFound, match="Missing dependencies"):
        repository._get_dependencies_from_lockfile(candidate)

    assert tuple(repository.dependency_generators()) == (repository._get_dependencies_from_lockfile,)


def test_matching_entries_for_named_requirement(mocker):
    repository = make_repository(mocker)
    demo = make_candidate()
    other = Candidate(parse_requirement("other"), name="other", version="1.0")
    repository.packages = {
        repository._identify_candidate(demo): Package(demo),
        repository._identify_candidate(other): Package(other),
    }

    assert list(repository._matching_entries(parse_requirement("demo"))) == [
        repository.packages[("demo", "1.0", None, False)]
    ]


def test_matching_entries_for_file_requirements(tmp_path, mocker):
    repository = make_repository(mocker)
    first_path = tmp_path / "first"
    second_path = tmp_path / "second"
    first_path.mkdir()
    second_path.mkdir()
    first = make_candidate(str(first_path))
    second = make_candidate(str(second_path))
    repository.packages = {
        ("demo", None, first_path.as_uri(), False): Package(first),
        ("demo", None, second_path.as_uri(), False): Package(second),
    }

    result = list(repository._matching_entries(parse_requirement(str(first_path))))

    assert result == [repository.packages[("demo", None, first_path.as_uri(), False)]]


def test_find_candidates_sets_file_requirement_name(mocker, tmp_path):
    repository = make_repository(mocker)
    path = tmp_path / "demo-1.0-py3-none-any.whl"
    locked = make_candidate(path.as_uri())
    requirement = parse_requirement(path.as_uri())
    mocker.patch.object(repository, "_matching_entries", return_value=[Package(locked)])
    mocker.patch.object(repository, "is_this_package", return_value=False)

    result = list(repository.find_candidates(requirement))

    assert result[0].name == "demo"
    assert requirement.name == "demo"


def test_find_candidates_prefers_current_project(mocker):
    repository = make_repository(mocker)
    candidate = make_candidate()
    mocker.patch.object(repository, "is_this_package", return_value=True)
    mocker.patch.object(repository, "make_this_candidate", return_value=candidate)
    matching = mocker.patch.object(repository, "_matching_entries")

    assert list(repository.find_candidates(parse_requirement("demo"))) == [candidate]
    matching.assert_not_called()


def test_evaluate_candidates_filters_packages(mocker):
    repository = make_repository(mocker)
    repository.environment.project.split_extras_groups.return_value = (["extra"], ["dev"])
    repository.environment.project.pyproject.resolution = {"excludes": ["excluded"]}

    def package(name, *, marker_matches=True, group_matches=True, groups=None):
        candidate = make_candidate(name)
        candidate.req.groups = groups or []
        candidate.req.marker = mocker.Mock()
        candidate.req.marker.matches.return_value = marker_matches
        group_marker = mocker.Mock()
        group_marker.evaluate.return_value = group_matches
        return Package(candidate, marker=group_marker)

    included = package("included", groups=["default"])
    repository.packages = {
        ("excluded", "1.0", None, False): package("excluded"),
        ("env-mismatch", "1.0", None, False): package("env-mismatch", marker_matches=False),
        ("group-marker", "1.0", None, False): package("group-marker", group_matches=False),
        ("wrong-group", "1.0", None, False): package("wrong-group", groups=["dev"]),
        ("included", "1.0", None, False): included,
    }

    result = list(repository.evaluate_candidates(["default"]))

    assert result == [included]


def test_evaluate_candidates_can_skip_environment_markers(mocker):
    repository = make_repository(mocker)
    repository.environment.project.split_extras_groups.return_value = ([], [])
    repository.environment.project.pyproject.resolution = {}
    candidate = make_candidate()
    candidate.req.marker = mocker.Mock()
    candidate.req.marker.matches.return_value = False
    package = Package(candidate)
    repository.packages = {("demo", "1.0", None, False): package}

    assert list(repository.evaluate_candidates(["default"], evaluate_markers=False)) == [package]


def test_merge_result_adds_and_merges_packages(mocker):
    repository = make_repository(mocker)
    env_spec = EnvSpec.current()
    existing = make_candidate("demo; python_version < '3.12'")
    existing.req.groups = ["default"]
    existing.hashes = [{"hash": "sha256:old"}]
    incoming = make_candidate("demo; python_version >= '3.10'")
    incoming.req.groups = ["dev"]
    incoming.hashes = [{"hash": "sha256:old"}, {"hash": "sha256:new"}]
    new_candidate = Candidate(parse_requirement("new"), name="new", version="1.0")
    repository.add_package(Package(existing))
    repository.__dict__["all_candidates"] = {"stale": []}

    repository.merge_result(env_spec, [Package(incoming), Package(new_candidate)])

    merged = repository.packages[repository._identify_candidate(existing)].candidate
    assert set(merged.req.groups) == {"default", "dev"}
    assert merged.hashes == [{"hash": "sha256:old"}, {"hash": "sha256:new"}]
    assert repository._identify_candidate(new_candidate) in repository.packages
    assert env_spec in repository.targets
    assert "all_candidates" not in repository.__dict__


def test_get_hashes_returns_candidate_hashes(mocker):
    repository = make_repository(mocker)
    candidate = make_candidate()
    candidate.hashes = [{"hash": "sha256:value"}]

    assert repository.get_hashes(candidate) is candidate.hashes
