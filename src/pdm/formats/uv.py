from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any, cast

import tomlkit

from pdm.models.candidates import Candidate
from pdm.models.markers import Marker, get_marker
from pdm.models.repositories import LockedRepository, Package
from pdm.models.requirements import FileRequirement, Requirement, VcsRequirement, parse_requirement, strip_extras
from pdm.project.core import Project
from pdm.utils import normalize_name


@dataclass
class _UvFileBuilder:
    project: Project
    requires_python: str
    requirements: list[Requirement]
    locked_repository: LockedRepository
    stack: ExitStack = field(default_factory=ExitStack, init=False)

    @cached_property
    def default_source(self) -> str:
        return cast(str, self.project.sources[0].url)

    def __post_init__(self) -> None:
        self._enter_path(self.project.root / "uv.lock")

    def build_pyproject_toml(self) -> Path:
        data = self.project.pyproject._data.unwrap()
        data.setdefault("project", {})["requires-python"] = self.requires_python
        data.setdefault("project", {})["dependencies"] = []
        data.setdefault("project", {}).pop("optional-dependencies", None)
        sources = {}
        collected_deps: dict[str, list[str]] = {}
        for dep in self.requirements:
            if isinstance(dep, FileRequirement):
                entry = self._get_name(dep)
                sources[entry] = self._build_source(dep)
            else:
                entry = dep.as_line()
            for group in dep.groups:
                collected_deps.setdefault(group, []).append(entry)

        for group, deps in collected_deps.items():
            if group == "default":
                data.setdefault("project", {})["dependencies"] = deps
            else:
                data.setdefault("project", {}).setdefault("optional-dependencies", {})[group] = deps

        if sources:
            data.setdefault("tool", {}).setdefault("uv", {}).setdefault("sources", {}).update(sources)

        path = self._enter_path(self.project.root / "pyproject.toml")
        with path.open("w", newline="") as f:
            tomlkit.dump(data, f)
        return path

    def _enter_path(self, path: Path) -> Path:
        if path.exists():
            backup = path.rename(path.with_name(f"{path.name}.bak"))
            self.stack.callback(backup.rename, path)
        else:
            self.stack.callback(path.unlink, True)
        return path

    def build_uv_lock(self) -> Path:
        locked_repo = self.locked_repository
        packages: list[dict[str, Any]] = []
        for key in locked_repo.packages:
            if "[" in key[0]:  # skip entries with extras
                continue
            # Merge related entries with the same name and version
            related_packages = [
                p for k, p in locked_repo.packages.items() if strip_extras(k[0])[0] == key[0] and k[1:] == key[1:]
            ]
            packages.append(self._build_lock_entry(related_packages))
        if name := self.project.name:
            version = self.project.pyproject.metadata.get("version", "0.0.0")
            this_package = {"name": normalize_name(name), "version": version, "source": {"editable": "."}}
            dependencies: list[dict[str, Any]] = []
            optional_dependencies: dict[str, list[dict[str, Any]]] = {}
            this_candidate = self.project.make_self_candidate(True)
            for req in self.requirements:
                group = req.groups[0]
                if (dep := self._make_dependency(this_candidate, req)) is None:
                    continue
                if group == "default":
                    dependencies.append(dep)
                else:
                    optional_dependencies.setdefault(group, []).append(dep)
            if dependencies:
                this_package["dependencies"] = dependencies  # type: ignore[assignment]
            if optional_dependencies:
                this_package["optional-dependencies"] = optional_dependencies
            packages.append(this_package)

        data = {"version": 1, "requires-python": self.requires_python}
        if packages:
            data["package"] = packages
        path = self.project.root / "uv.lock"
        with path.open("w", newline="") as f:
            tomlkit.dump(data, f)
        return path

    def _get_name(self, req: FileRequirement) -> str:
        if req.key:
            return req.key
        can = Candidate(req).prepare(self.project.environment)
        return normalize_name(can.metadata.name)

    def _build_source(self, req: FileRequirement) -> dict[str, Any]:
        result: dict[str, Any]
        if isinstance(req, VcsRequirement):
            result = {req.vcs: req.repo}
            if req.ref:
                result["rev"] = req.ref
        elif req.path:
            result = {"path": req.str_path}
        else:
            result = {"url": req.url}
        if req.editable:
            result["editable"] = True
        return result

    def _build_lock_source(self, req: Requirement) -> dict[str, Any]:
        if isinstance(req, VcsRequirement):
            return {req.vcs: f"{req.repo}?rev={req.ref}#{req.revision}"}
        elif isinstance(req, FileRequirement):
            if req.editable:
                return {"editable": req.str_path}
            else:
                return {"url": req.url}
        else:
            return {"registry": self.default_source}

    def _build_lock_entry(self, packages: list[Package]) -> dict[str, Any]:
        packages.sort(key=lambda x: len(x.candidate.req.extras or []))
        candidate = packages[0].candidate
        req = candidate.req
        result: dict[str, Any] = {
            "name": candidate.name,
            "version": candidate.version,
            "source": self._build_lock_source(req),
        }
        for file_hash in candidate.hashes:
            filename = file_hash.get("url", file_hash.get("file", ""))
            is_wheel = filename.endswith(".whl")
            item = {"url": file_hash.get("url", filename), "hash": file_hash["hash"]}
            if is_wheel:
                result.setdefault("wheels", []).append(item)
            else:
                result["sdist"] = item
        optional_dependencies: dict[str, list[dict[str, Any]]] = {}
        for package in packages:
            if not package.candidate.req.extras:
                deps = [
                    self._make_dependency(package.candidate, parse_requirement(dep)) for dep in package.dependencies
                ]
                result["dependencies"] = [dep for dep in deps if dep is not None]
            else:
                deps = [
                    self._make_dependency(package.candidate, parse_requirement(dep))
                    for dep in package.dependencies
                    if parse_requirement(dep).key != candidate.req.key
                ]
                deps = [dep for dep in deps if dep is not None]
                for extra in package.candidate.req.extras:
                    # XXX: when depending on a package with extras, the extra dependencies are encoded in
                    # the corresponding group under optional-dependencies. But in case multiple extras are requested,
                    # the same dependencies get duplicated in those groups, but it's okay if each single extra is
                    # never requested alone.
                    if extra not in optional_dependencies:
                        optional_dependencies[extra] = deps  # type: ignore[assignment]

        if optional_dependencies:
            result["optional-dependencies"] = optional_dependencies
        return result

    def _make_dependency(self, candidate: Candidate, req: Requirement) -> dict[str, Any] | None:
        locked_repo = self.locked_repository
        parent_marker = (req.marker or get_marker("")) & (candidate.req.marker or get_marker(""))
        matching_entries = [e for k, e in locked_repo.packages.items() if k[0] == req.key]

        def marker_match(marker: Marker | None) -> bool:
            return not (parent_marker & (marker or get_marker("")).is_empty())

        if not matching_entries:
            return None
        result: dict[str, Any] = {}
        if len(matching_entries) == 1:
            candidate = matching_entries[0].candidate
            multiple = False
        else:
            candidate = next(e.candidate for e in matching_entries if marker_match(e.candidate.req.marker))
            multiple = True
        result.update({"name": candidate.name})
        if multiple:
            result.update(version=candidate.version, source=self._build_lock_source(candidate.req))
        if req.extras:
            result["extra"] = list(req.extras)
        if req.marker is not None:
            result["marker"] = str(req.marker)
        return result


@contextmanager
def uv_file_builder(
    project: Project, requires_python: str, requirements: list[Requirement], locked_repository: LockedRepository
) -> Iterator[_UvFileBuilder]:
    builder = _UvFileBuilder(project, requires_python, requirements, locked_repository)
    with builder.stack:
        yield builder
