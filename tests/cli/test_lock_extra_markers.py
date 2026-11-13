from __future__ import annotations

import hashlib

import pytest

from pdm.cli import actions
from pdm.models.caches import CandidateInfoCache
from pdm.models.candidates import Candidate
from pdm.models.markers import EnvSpec, get_marker
from pdm.models.requirements import parse_requirement
from pdm.project.lockfile import FLAG_INHERIT_METADATA
from pdm.project.lockfile.base import Compatibility
from pdm.utils import parse_version


@pytest.fixture
def extra_dependencies(repository):
    for name in ("foo", "base", "bar-dep", "qux-dep", "shared", "conditional", "unrelated"):
        repository.add_candidate(name, "1.0")
    dependencies = [
        'bar-dep; extra == "bar"',
        'qux-dep; extra == "qux"',
        'shared; extra == "bar" or extra == "qux"',
        'conditional; (extra == "bar" and os_name == "nt") or (extra == "qux" and os_name == "posix")',
    ]
    repository.add_dependencies("foo", "1.0", ["base", *dependencies])
    return dependencies


@pytest.mark.parametrize("inherit_metadata", [False, True])
def test_lock_preserves_extra_markers(project, extra_dependencies, inherit_metadata):
    project.add_dependencies(["foo[bar,qux]"])
    actions.do_lock(project, strategy_change=["inherit_metadata" if inherit_metadata else "no_inherit_metadata"])

    packages = {p.candidate.identify(): p for p in project.get_locked_repository().packages.values()}
    assert set(packages) == {"foo", "foo[bar,qux]", "base", "bar-dep", "qux-dep", "shared", "conditional"}
    assert packages["foo[bar,qux]"].dependencies == sorted(
        ["foo==1.0", *(parse_requirement(line).as_line() for line in extra_dependencies)]
    )
    assert packages["foo"].dependencies == ["base"]
    assert all(p.candidate.req.marker is None or "extra" not in str(p.candidate.req.marker) for p in packages.values())

    # Reuse must keep the original dependency metadata when reading the lock again.
    actions.do_lock(project, strategy="reuse")
    reused = {p.candidate.identify(): p for p in project.get_locked_repository().packages.values()}
    assert reused["foo[bar,qux]"].dependencies == packages["foo[bar,qux]"].dependencies


@pytest.mark.parametrize("inherit_metadata", [False, True])
@pytest.mark.parametrize("platform", ["windows_amd64", "manylinux_2_17_x86_64"])
@pytest.mark.parametrize("extra", ["bar", "qux"])
def test_install_from_lock_evaluates_parent_extras(project, extra_dependencies, inherit_metadata, platform, extra):
    project.add_dependencies([f"foo[{extra}]"])
    project.add_dependencies(["unrelated"], to_group="optional")
    actions.do_lock(
        project,
        groups=["default", "optional"],
        strategy_change=["inherit_metadata" if inherit_metadata else "no_inherit_metadata"],
    )
    candidates = actions.resolve_candidates_from_lockfile(
        project,
        project.get_dependencies(),
        groups=["default"],
        env_spec=EnvSpec.from_spec(">=3.10", platform=platform),
    )
    expected = {"foo", f"foo[{extra}]", "base", f"{extra}-dep", "shared"}
    if (extra == "bar") == (platform == "windows_amd64"):
        expected.add("conditional")
    assert set(candidates) == expected


def test_dependency_cache_does_not_reuse_stripped_extra_markers(project, extra_dependencies):
    candidate = Candidate(parse_requirement("foo[bar,qux]"), "foo", "1.0")
    python_hash = hashlib.sha1(str(project.environment.python_requires).encode()).hexdigest()
    old_cache = CandidateInfoCache(project.cache("metadata") / f"package_meta_{python_hash}.json")
    old_cache.set(candidate, (["bar-dep", "qux-dep", "shared", "conditional"], "", ""))
    project.add_dependencies(["foo[bar,qux]"])
    actions.do_lock(project)
    packages = {p.candidate.identify(): p for p in project.get_locked_repository().packages.values()}
    assert any(
        parse_requirement(line).marker == get_marker('extra == "bar"') for line in packages["foo[bar,qux]"].dependencies
    )


def test_read_legacy_lock_without_extra_markers(project, extra_dependencies):
    project.add_dependencies(["foo[bar,qux]"])
    actions.do_lock(project, strategy_change=["no_inherit_metadata"])
    data = project.lockfile._data
    for package in data["package"]:
        for index, line in enumerate(package.get("dependencies", [])):
            req = parse_requirement(line)
            if req.marker:
                marker = req.marker.split_extras()[0]
                req.marker = marker if not marker.is_any() else None
                package["dependencies"][index] = req.as_line()
    data["metadata"]["lock_version"] = "4.5.1"
    project.lockfile.write()
    project.lockfile.reload()
    assert FLAG_INHERIT_METADATA not in project.lockfile.strategy
    candidates = actions.resolve_candidates_from_lockfile(project, project.get_dependencies())
    assert {"foo", "foo[bar,qux]", "base", "bar-dep", "qux-dep", "shared"} <= set(candidates)


def test_extra_marker_lock_requires_a_compatible_reader(project, extra_dependencies, monkeypatch):
    project.add_dependencies(["foo[bar,qux]"])
    actions.do_lock(project)
    monkeypatch.setattr(project.lockfile, "spec_version", parse_version("4.5.1"))
    assert project.lockfile.compatibility() == Compatibility.NONE


def test_export_uses_evaluated_extra_markers(project, extra_dependencies, pdm):
    project.add_dependencies(["foo[bar]"])
    actions.do_lock(project)
    result = pdm(["export", "--without-hashes"], obj=project, strict=True)
    requirements = [
        parse_requirement(line) for line in result.output.splitlines() if line and not line.startswith(("#", "-"))
    ]
    assert {req.key for req in requirements} == {"foo", "base", "bar-dep", "shared", "conditional"}
    assert next(req for req in requirements if req.key == "conditional").marker == get_marker('os_name == "nt"')
    assert all(req.marker is None or req.marker.inner.only("extra").is_any() for req in requirements)


@pytest.mark.parametrize("platform", ["windows_amd64", "manylinux_2_17_x86_64"])
def test_pylock_distinguishes_project_and_dependency_extras(project, extra_dependencies, platform):
    project.project_config["lock.format"] = "pylock"
    project.add_dependencies(["unrelated"])
    project.add_dependencies(["foo[bar]"], to_group="feature")
    actions.do_lock(project, groups=["default", "feature"])
    assert all(
        get_marker(package.get("marker", "")).inner.only("extra").is_any()
        for package in project.lockfile._data["packages"]
    )
    candidates = actions.resolve_candidates_from_lockfile(
        project,
        project.get_dependencies("feature"),
        groups=["feature"],
        env_spec=EnvSpec.from_spec(">=3.10", platform=platform),
    )
    expected = {"foo", "base", "bar-dep", "shared"}
    if platform == "windows_amd64":
        expected.add("conditional")
    assert set(candidates) == expected
