from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime, time
from typing import TYPE_CHECKING, Any

from dep_logic.markers import AnyMarker, BaseMarker, MarkerUnion

from pdm.exceptions import PdmException, RequirementError
from pdm.models.requirements import (
    ALLOW_ANY,
    FileRequirement,
    NamedRequirement,
    Requirement,
    VcsRequirement,
    parse_requirement,
)
from pdm.utils import cd, get_file_hash, get_requirement_from_override, normalize_name, url_without_fragments

if TYPE_CHECKING:
    from pathlib import Path

    from pdm.models.repositories.lock import LockedRepository, Package
    from pdm.project import Project


_URL_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://")
_OPAQUE_REQUIREMENT_PREFIX = "url-sha256:"
_DYNAMIC_LOCK_FIELDS = frozenset({"dependencies", "optional-dependencies", "requires-python", "version"})


def _to_builtin(value: Any, *, allow_temporal: bool = False) -> Any:
    if hasattr(value, "unwrap"):
        value = value.unwrap()
    if isinstance(value, Mapping):
        return {key: _to_builtin(item, allow_temporal=allow_temporal) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_builtin(item, allow_temporal=allow_temporal) for item in value]
    if allow_temporal and isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if value is None or isinstance(value, (bool, float, int, str)):
        return value
    raise TypeError(f"Unsupported lock input type: {type(value).__name__}")


def _fingerprint(value: str, prefix: str = "sha256:") -> str:
    return prefix + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _requirement_input(requirement: Requirement) -> str:
    line = requirement.as_line()
    if isinstance(requirement, NamedRequirement) and not _URL_RE.search(line):
        return dataclasses.replace(requirement, specifier=ALLOW_ANY).as_line()
    if isinstance(requirement, FileRequirement) and not requirement.url and requirement.path is not None:
        line = json.dumps(
            {
                "editable": requirement.editable,
                "extras": sorted(requirement.extras or []),
                "marker": str(requirement.marker or ""),
                "name": requirement.project_name or "",
                "path": requirement.str_path,
                "subdirectory": requirement.subdirectory or "",
            },
            sort_keys=True,
        )
    return _fingerprint(line, _OPAQUE_REQUIREMENT_PREFIX)


def _sanitize_strings(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _sanitize_strings(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_strings(item) for item in value]
    if isinstance(value, str) and _URL_RE.search(value):
        return _fingerprint(value)
    return value


def _normalize_sources(sources: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for source in sources:
        item = dict(source)
        item.pop("username", None)
        item.pop("password", None)
        if url := item.get("url"):
            item["url"] = _fingerprint(str(url))
        for key in ("include_packages", "exclude_packages"):
            if key in item:
                item[key] = sorted(item[key])
        result.append(_sanitize_strings(item))
    return result


def _project_lock_inputs(
    project: Project,
    include_package: bool = False,
    managed_paths: frozenset[Path] = frozenset(),
) -> dict[str, Any]:
    dependencies = project._resolve_dependencies()
    resolution = _to_builtin(project.pyproject.resolution, allow_temporal=True)
    resolution.pop("lock_inputs", None)
    with cd(project.root):
        groups = {
            group: sorted(_requirement_input(requirement) for requirement in requirements)
            for group, requirements in sorted(dependencies.items())
        }

    result: dict[str, Any] = {
        "groups": groups,
        "requires-python": str(project.python_requires),
        "resolution": _sanitize_strings(resolution),
        "sources": _normalize_sources(_to_builtin(project.pyproject.settings.get("source", []), allow_temporal=True)),
    }
    if include_package:
        metadata = project.pyproject.metadata
        dynamic = sorted(metadata.get("dynamic", []))
        result["package"] = {
            "build-system": _sanitize_strings(_to_builtin(project.pyproject.build_system, allow_temporal=True)),
            "distribution": project.is_distribution,
            "dynamic": dynamic,
            "name": metadata.get("name", ""),
            "version": metadata.get("version", ""),
        }
        if _DYNAMIC_LOCK_FIELDS.intersection(dynamic):
            result["volatile"] = True

    local_inputs: dict[str, Any] = {}
    for requirements in dependencies.values():
        for requirement in requirements:
            if not isinstance(requirement, FileRequirement) or requirement.absolute_path is None:
                continue
            path = requirement.absolute_path.resolve()
            if path in managed_paths:
                continue
            key = _requirement_input(requirement)
            if path.is_file():
                local_inputs[key] = {"file-sha256": get_file_hash(path)}
            elif path.is_dir():
                local_project = project.core.create_project(path)
                if local_project.pyproject.is_valid:
                    local_inputs[key] = _project_lock_inputs(
                        local_project,
                        include_package=True,
                        managed_paths=managed_paths | {path},
                    )
                else:
                    local_inputs[key] = {"volatile": True}
    if local_inputs:
        result["local"] = {key: local_inputs[key] for key in sorted(local_inputs)}
    return result


def build_lock_inputs(project: Project) -> dict[str, Any]:
    """Build the canonical project inputs that determine a lock resolution."""
    workspace_project = project.workspace_project or project
    root = workspace_project.root.resolve()
    members = (
        sorted(workspace_project.iter_members(), key=lambda path: path.relative_to(root).as_posix())
        if workspace_project.is_workspace_root
        else []
    )
    managed_paths = frozenset({root, *(member.resolve() for member in members)})
    result: dict[str, Any] = {
        "project": _project_lock_inputs(workspace_project, managed_paths=managed_paths),
    }
    if members:
        result["workspace"] = {
            member.relative_to(root).as_posix(): _project_lock_inputs(
                workspace_project.core.create_project(member),
                include_package=True,
                managed_paths=managed_paths,
            )
            for member in members
        }
    return result


def _contains_volatile(value: Any) -> bool:
    if isinstance(value, Mapping):
        return value.get("volatile") is True or any(_contains_volatile(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_volatile(item) for item in value)
    return False


def _requirements_match(
    current_lines: Sequence[str],
    locked_lines: Sequence[str],
) -> bool:
    if len(current_lines) != len(locked_lines):
        return False
    if not all(isinstance(line, str) for line in (*current_lines, *locked_lines)):
        return False
    return sorted(current_lines) == sorted(locked_lines)


def _project_inputs_match(
    current: Mapping[str, Any],
    locked: Mapping[str, Any],
) -> bool:
    current_metadata = {key: value for key, value in current.items() if key != "groups"}
    locked_metadata = {key: value for key, value in locked.items() if key != "groups"}
    if current_metadata != locked_metadata:
        return False

    current_groups = current.get("groups")
    locked_groups = locked.get("groups")
    if not isinstance(current_groups, Mapping) or not isinstance(locked_groups, Mapping):
        return False
    if current_groups.keys() != locked_groups.keys():
        return False
    return all(
        isinstance(current_groups[group], Sequence)
        and not isinstance(current_groups[group], str)
        and isinstance(locked_groups[group], Sequence)
        and not isinstance(locked_groups[group], str)
        and _requirements_match(current_groups[group], locked_groups[group])
        for group in current_groups
    )


def _project_overrides(project: Project) -> dict[str, Requirement] | None:
    result: dict[str, Requirement] = {}
    try:
        with cd(project.root):
            for name, value in project.pyproject.resolution.get("overrides", {}).items():
                requirement = parse_requirement(get_requirement_from_override(normalize_name(name), value))
                result[requirement.identify()] = requirement
    except (RequirementError, TypeError, ValueError):
        return None
    return result


def _effective_requirement(requirement: Requirement, overrides: Mapping[str, Requirement]) -> Requirement:
    effective = overrides.get(requirement.identify())
    if effective is None and requirement.key is not None:
        effective = overrides.get(requirement.key)
    return requirement if effective is None else effective


def _requirement_is_excluded(requirement: Requirement, excludes: frozenset[str]) -> bool:
    return requirement.identify() in excludes or (requirement.key is not None and requirement.key in excludes)


def _requirement_marker(requirement: Requirement) -> BaseMarker:
    return requirement.marker.inner if requirement.marker is not None else AnyMarker()


def _package_marker(package: Package) -> BaseMarker:
    marker = package.candidate.req.marker
    return marker.inner if marker is not None else AnyMarker()


def _applicable_regions(requirement: Requirement, repository: LockedRepository) -> list[BaseMarker] | None:
    if not repository.targets:
        return None
    requirement_marker = _requirement_marker(requirement)
    regions: list[BaseMarker] = []
    for target in repository.targets:
        region = requirement_marker & target.markers_with_python().inner
        if not region.is_empty():
            regions.append(region)
    return regions


def _package_matches_requirement_context(
    package: Package,
    requirement: Requirement,
    project: Project,
    group: str,
) -> bool:
    candidate = package.candidate
    if requirement.key is not None and normalize_name(candidate.name or "") != requirement.key:
        return False
    if candidate.req.groups and group not in candidate.req.groups:
        return False
    extras, dependency_groups = project.split_extras_groups([group])
    if not package.marker.evaluate({"extras": set(extras), "dependency_groups": set(dependency_groups)}):
        return False
    return True


def _context_packages(
    requirement: Requirement,
    project: Project,
    group: str,
    repository: LockedRepository,
    regions: Sequence[BaseMarker],
) -> list[Package]:
    return [
        package
        for package in repository.packages.values()
        if _package_matches_requirement_context(package, requirement, project, group)
        and any(not (region & _package_marker(package)).is_empty() for region in regions)
    ]


def _packages_cover_regions(packages: Sequence[Package], regions: Sequence[BaseMarker]) -> bool:
    if not packages:
        return False
    coverage = MarkerUnion.of(*(_package_marker(package) for package in packages))
    return all((region & coverage) == region for region in regions)


def _file_source_identity(requirement: FileRequirement, project: Project) -> tuple[Any, ...]:
    common = (requirement.editable, requirement.subdirectory or "")
    if requirement.absolute_path is not None:
        return ("path", requirement.absolute_path.resolve(), *common)
    if isinstance(requirement, VcsRequirement):
        repo = project.backend.expand_line(url_without_fragments(requirement.repo))
        return ("vcs", requirement.vcs, repo, requirement.ref or "", *common)
    url = project.backend.expand_line(url_without_fragments(requirement.get_full_url()))
    return ("url", url, *common)


def _requirement_matches(
    requirement: Requirement,
    effective: Requirement,
    project: Project,
    group: str,
    repository: LockedRepository,
) -> bool:
    regions = _applicable_regions(requirement, repository)
    if regions is None:
        return False
    if not regions:
        return True
    packages = _context_packages(requirement, project, group, repository, regions)
    if isinstance(effective, NamedRequirement):
        if not all(
            package.candidate.version is not None
            and effective.specifier.contains(package.candidate.version, prereleases=True)
            for package in packages
        ):
            return False
    elif isinstance(effective, FileRequirement):
        expected_source = _file_source_identity(effective, project)
        packages = [
            package
            for package in packages
            if isinstance(package.candidate.req, FileRequirement)
            and _file_source_identity(package.candidate.req, project) == expected_source
        ]
    else:  # pragma: no cover
        return False
    return _packages_cover_regions(packages, regions)


def _project_specifiers_match(
    project: Project,
    repository: LockedRepository,
    overrides: Mapping[str, Requirement],
    excludes: frozenset[str],
    managed_paths: frozenset[Path],
    groups: Sequence[str],
) -> bool:
    dependencies = project._resolve_dependencies(list(groups))
    for group, requirements in dependencies.items():
        for requirement in requirements:
            if _requirement_is_excluded(requirement, excludes):
                continue
            effective = _effective_requirement(requirement, overrides)
            if not _requirement_matches(requirement, effective, project, group, repository):
                return False
            if not isinstance(effective, FileRequirement) or effective.absolute_path is None:
                continue
            path = effective.absolute_path.resolve()
            if path in managed_paths or not path.is_dir():
                continue
            local_project = project.core.create_project(path)
            if not local_project.pyproject.is_valid:
                return False
            if not _project_specifiers_match(
                local_project,
                repository,
                overrides,
                excludes,
                managed_paths | {path},
                ["default"],
            ):
                return False
    return True


def _all_specifiers_match(project: Project, repository: LockedRepository) -> bool:
    root = project.root.resolve()
    members = (
        sorted(project.iter_members(), key=lambda path: path.relative_to(root).as_posix())
        if project.is_workspace_root
        else []
    )
    managed_paths = frozenset({root, *(member.resolve() for member in members)})
    overrides = _project_overrides(project)
    if overrides is None:
        return False
    excludes = frozenset(normalize_name(name) for name in project.pyproject.resolution.get("excludes", []))
    if not _project_specifiers_match(
        project,
        repository,
        overrides,
        excludes,
        managed_paths,
        project.lockfile.groups or ["default"],
    ):
        return False
    return all(
        _project_specifiers_match(
            project.core.create_project(member),
            repository,
            overrides,
            excludes,
            managed_paths,
            ["default"],
        )
        for member in members
    )


def lock_inputs_match(project: Project, locked_inputs: object) -> bool:
    """Return whether the current project is satisfied by the recorded lock inputs."""
    try:
        locked = _to_builtin(locked_inputs)
    except (TypeError, ValueError):
        return False
    if not isinstance(locked, Mapping):
        return False
    current = build_lock_inputs(project)
    if _contains_volatile(current) or _contains_volatile(locked):
        return False

    workspace_project = project.workspace_project or project
    if current != locked:
        current_project = current.get("project")
        locked_project = locked.get("project")
        if not isinstance(current_project, Mapping) or not isinstance(locked_project, Mapping):
            return False
        if not _project_inputs_match(current_project, locked_project):
            return False

        current_workspace = current.get("workspace", {})
        locked_workspace = locked.get("workspace", {})
        if not isinstance(current_workspace, Mapping) or not isinstance(locked_workspace, Mapping):
            return False
        if current_workspace.keys() != locked_workspace.keys():
            return False
        if not all(
            isinstance(current_workspace[path], Mapping)
            and isinstance(locked_workspace[path], Mapping)
            and _project_inputs_match(current_workspace[path], locked_workspace[path])
            for path in current_workspace
        ):
            return False

    try:
        return _all_specifiers_match(workspace_project, workspace_project.get_locked_repository())
    except (PdmException, TypeError, ValueError):
        return False
