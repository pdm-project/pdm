from __future__ import annotations

import hashlib
import shutil
import tarfile

import pytest
from unearth.errors import HashMismatchError

from pdm.exceptions import CandidateNotFound, RequirementError
from pdm.models.candidates import Candidate
from pdm.models.markers import EnvSpec
from pdm.models.repositories.lock import LockedRepository, Package
from pdm.models.requirements import parse_requirement
from pdm.models.specifiers import PySpecSet
from tests import FIXTURES


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


def test_merge_result_keeps_packages_out_of_foreign_targets(mocker):
    repository = make_repository(mocker)
    windows = EnvSpec.from_spec(requires_python=">=3.9", platform="windows")
    linux = EnvSpec.from_spec(requires_python=">=3.9", platform="linux")

    def candidate(name):
        return Candidate(parse_requirement(name), name=name, version="1.0")

    shared, windows_only = candidate("shared"), candidate("windows-only")
    marked = candidate("marked")
    marked.req = parse_requirement("marked; sys_platform == 'win32'")
    repository.merge_result(windows, [Package(shared), Package(windows_only), Package(marked)])

    # The first target doesn't restrict anything, there is nothing to be excluded from yet.
    assert all(can.req.marker is None for can in (shared, windows_only))

    linux_only = candidate("linux-only")
    repository.merge_result(linux, [Package(candidate("shared")), Package(linux_only)])

    # A package resolved for the new target only, without a marker excluding the old ones.
    assert str(linux_only.req.marker) == 'sys_platform == "linux"'
    # A package missing from the new target's resolution.
    assert str(windows_only.req.marker) == 'sys_platform != "linux"'
    # Markers that already exclude the other target are left alone.
    assert str(marked.req.marker) == 'sys_platform == "win32"'
    # Packages resolved for both targets stay unrestricted.
    assert repository.packages[repository._identify_candidate(shared)].candidate.req.marker is None


def test_merge_result_keeps_packages_in_targets_sharing_the_platform(mocker):
    repository = make_repository(mocker)
    manylinux = EnvSpec.from_spec(requires_python=">=3.9", platform="linux")
    musllinux = EnvSpec.from_spec(requires_python=">=3.9", platform="alpine")

    def candidate(name, version="1.0"):
        return Candidate(parse_requirement(name), name=name, version=version)

    manylinux_only = candidate("forked", "2.0")
    repository.merge_result(manylinux, [Package(candidate("shared")), Package(manylinux_only)])
    musllinux_only = candidate("forked", "1.0")
    repository.merge_result(musllinux, [Package(candidate("shared")), Package(musllinux_only)])

    # Both targets are x86_64 Linux, a platform marker excluding the new target
    # would also exclude the one the package was resolved for.
    assert manylinux_only.req.marker is None or manylinux_only.req.marker.matches(manylinux)
    assert musllinux_only.req.marker.matches(musllinux)


def test_get_hashes_returns_candidate_hashes(mocker):
    repository = make_repository(mocker)
    candidate = make_candidate()
    candidate.hashes = [{"hash": "sha256:value"}]

    assert repository.get_hashes(candidate) is candidate.hashes


@pytest.mark.parametrize("source", ["url", "path"])
@pytest.mark.parametrize("hashes", [{"sha256": "a" * 64}, {"sha256": "a" * 64, "sha512": "b" * 128}])
def test_read_pylock_archive_hashes(project, source, hashes):
    filename = "demo-1.0.tar.gz"
    if source == "url":
        archive = {"url": f"https://example.org/{filename}#subdirectory=src"}
    else:
        (project.root / filename).touch()
        archive = {"path": filename}
    lockfile = {
        "lock-version": "1.0",
        "created-by": "pdm",
        "packages": [{"name": "demo", "version": "1.0", "archive": {**archive, "hashes": hashes}}],
    }

    repository = LockedRepository(lockfile, [], project.environment)
    candidate = next(iter(repository.packages.values())).candidate
    link = candidate.link

    assert link is not None
    assert candidate.hashes == [
        {"url": link.url_without_fragment, "file": filename, "hash": f"{algo}:{value}"}
        for algo, value in hashes.items()
    ]


@pytest.mark.parametrize("artifact_type", ["wheels", "sdist"])
@pytest.mark.parametrize("source", ["url", "relative-path", "absolute-path", "path-and-url"])
@pytest.mark.parametrize("lock_directory", [".", "locks"])
def test_read_pylock_artifact_locations(project, artifact_type, source, lock_directory):
    lock_root = project.root / lock_directory
    project.set_lockfile(lock_root / "pylock.toml")
    filename = "demo-1.0-py3-none-any.whl" if artifact_type == "wheels" else "demo-1.0.tar.gz"
    path = lock_root / "local artifacts" / filename
    url = f"https://example.org/{filename}"
    artifact = {"hashes": {"sha256": "a" * 64}}
    if source == "url":
        artifact["url"] = url
    else:
        artifact["path"] = path.as_posix() if source == "absolute-path" else f"local artifacts/{filename}"
        if source == "path-and-url":
            artifact["url"] = url
    package = {"name": "demo", "version": "1.0"}
    package[artifact_type] = [artifact] if artifact_type == "wheels" else artifact
    lockfile = {"lock-version": "1.0", "created-by": "test", "packages": [package]}

    repository = LockedRepository(lockfile, [], project.environment)
    candidate = next(iter(repository.packages.values())).candidate

    assert candidate.hashes == [{"hash": "sha256:" + "a" * 64, "url": url if source == "url" else path.as_uri()}]


@pytest.mark.parametrize("with_url", [False, True])
@pytest.mark.parametrize("lock_directory", [".", "locks"])
def test_read_pylock_local_wheel_can_be_built(project, mocker, with_url, lock_directory):
    artifact = FIXTURES / "artifacts/first-2.0.2-py2.py3-none-any.whl"
    lock_root = project.root / lock_directory
    project.set_lockfile(lock_root / "pylock.toml")
    directory = lock_root / "local artifacts"
    directory.mkdir(parents=True)
    wheel = directory / artifact.name
    shutil.copy2(artifact, wheel)
    wheel_data = {
        "path": f"local artifacts/{wheel.name}",
        "hashes": {"sha256": hashlib.sha256(wheel.read_bytes()).hexdigest()},
    }
    if with_url:
        wheel_data["url"] = f"https://example.org/{wheel.name}"
    lockfile = {
        "lock-version": "1.0",
        "created-by": "test",
        "packages": [{"name": "first", "version": "2.0.2", "wheels": [wheel_data]}],
    }
    repository = LockedRepository(lockfile, [], project.environment)
    candidate = next(iter(repository.packages.values())).candidate
    find_match = mocker.patch(
        "unearth.PackageFinder.find_best_match", side_effect=AssertionError("Unexpected index lookup")
    )

    built = candidate.prepare(project.environment).build()

    assert built.read_bytes() == wheel.read_bytes()
    find_match.assert_not_called()


@pytest.mark.parametrize("artifact_type", ["wheels", "sdist"])
@pytest.mark.parametrize("with_url", [False, True], ids=["path-only", "path-and-url"])
@pytest.mark.parametrize("bad_hash", [False, True], ids=["good-hash", "bad-hash"])
@pytest.mark.parametrize("physical_filename", ["0123456789abcdef", "wrong.tar.bz2"])
def test_read_pylock_local_artifact_with_explicit_name(
    project, mocker, artifact_type, with_url, bad_hash, physical_filename
):
    is_wheel = artifact_type == "wheels"
    name, version = ("first", "2.0.2") if is_wheel else ("demo", "0.0.1")
    filename = f"{name}-{version}-py2.py3-none-any.whl" if is_wheel else f"{name}-{version}.tar.gz"
    artifact = FIXTURES / "artifacts" / filename
    content = artifact.read_bytes()
    lock_root = project.root / "locks"
    project.set_lockfile(lock_root / "pylock.toml")
    path = lock_root / "local artifacts" / physical_filename
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    artifact_data = {
        "name": filename,
        "path": f"local artifacts/{path.name}",
        "hashes": {"sha256": "0" * 64 if bad_hash else hashlib.sha256(content).hexdigest()},
    }
    if with_url:
        # This URL is served by the test fixture, but must never replace the local path.
        artifact_data["url"] = f"http://fixtures.test/artifacts/{filename}"
    package = {"name": name, "version": version, artifact_type: [artifact_data] if is_wheel else artifact_data}
    lockfile = {"lock-version": "1.0", "created-by": "test", "packages": [package]}
    repository = LockedRepository(lockfile, [], project.environment)
    candidate = next(iter(repository.packages.values())).candidate
    find_match = mocker.patch(
        "unearth.PackageFinder.find_best_match", side_effect=AssertionError("Unexpected index lookup")
    )
    prepared = candidate.prepare(project.environment)

    if bad_hash:
        with pytest.raises(HashMismatchError, match="Hash mismatch"):
            prepared._obtain(allow_all=False)
    elif is_wheel:
        built = prepared.build()
        assert built.name == filename
        assert built.read_bytes() == content
    else:
        prepared._obtain(allow_all=False)
        assert prepared._unpacked_dir is not None
        with tarfile.open(artifact) as archive:
            for member in ("setup.py", "demo.py"):
                expected = archive.extractfile(f"{name}-{version}/{member}")
                assert expected is not None
                assert (prepared._unpacked_dir / member).read_bytes() == expected.read()

    assert prepared.link is not None
    assert prepared.link.file_path == path
    assert prepared.link.filename == filename
    assert path.read_bytes() == content
    find_match.assert_not_called()


@pytest.mark.parametrize("artifact_type", ["wheels", "sdist"])
@pytest.mark.parametrize(
    "filename",
    [
        "../first-2.0.2-py2.py3-none-any.whl",
        "..\\first-2.0.2-py2.py3-none-any.whl",
        "C:first-2.0.2-py2.py3-none-any.whl",
        "",
        ".",
        "..",
        "first\u0000.whl",
    ],
    ids=["parent-posix", "parent-windows", "drive-relative", "empty", "dot", "parent", "nul"],
)
def test_read_pylock_rejects_unsafe_artifact_name_before_io(project, mocker, artifact_type, filename):
    artifact = {"name": filename, "path": "cache/opaque", "hashes": {"sha256": "a" * 64}}
    package = {
        "name": "first",
        "version": "2.0.2",
        artifact_type: [artifact] if artifact_type == "wheels" else artifact,
    }
    repository = LockedRepository(
        {"lock-version": "1.0", "created-by": "test", "packages": [package]}, [], project.environment
    )
    candidate = next(iter(repository.packages.values())).candidate
    prepared = candidate.prepare(project.environment)
    find_match = mocker.patch(
        "unearth.PackageFinder.find_best_match", side_effect=AssertionError("Unexpected index lookup")
    )
    cache = mocker.patch.object(prepared, "_get_build_cache", side_effect=AssertionError("Unexpected cache access"))
    unpack = mocker.patch.object(prepared, "_unpack", side_effect=AssertionError("Unexpected artifact IO"))

    with pytest.raises(RequirementError, match="Invalid artifact filename"):
        prepared.build()

    find_match.assert_not_called()
    cache.assert_not_called()
    unpack.assert_not_called()
