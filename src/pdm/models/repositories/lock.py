from __future__ import annotations

import dataclasses
import os
import posixpath
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Collection, NamedTuple, cast

from pdm.exceptions import CandidateNotFound, PdmException
from pdm.models.candidates import Candidate
from pdm.models.markers import EnvSpec
from pdm.models.repositories.base import BaseRepository, CandidateMetadata
from pdm.models.requirements import FileRequirement, Requirement, parse_line
from pdm.utils import cd, path_to_url, url_to_path, url_without_fragments

if TYPE_CHECKING:
    from typing import Any, Callable, Iterable, Mapping

    from tomlkit.toml_document import TOMLDocument

    from pdm._types import FileHash, RepositoryConfig
    from pdm.environments import BaseEnvironment

    CandidateKey = tuple[str, str | None, str | None, bool]


class PackageEntry(NamedTuple):
    candidate: Candidate
    dependencies: list[str]
    summary: str


class LockedRepository(BaseRepository):
    def __init__(
        self,
        lockfile: Mapping[str, Any],
        sources: list[RepositoryConfig],
        environment: BaseEnvironment,
        env_spec: EnvSpec | None = None,
    ) -> None:
        super().__init__(sources, environment, env_spec=env_spec or environment.spec)
        self.packages: dict[CandidateKey, PackageEntry] = {}
        self.targets: list[EnvSpec] = []
        self._read_lockfile(lockfile)

    @cached_property
    def all_candidates(self) -> dict[str, list[Candidate]]:
        """Return a dict of all candidates grouped by the package name."""
        result: dict[str, list[Candidate]] = {}
        for entry in self.packages.values():
            result.setdefault(entry.candidate.identify(), []).append(entry.candidate)
        return result

    @property
    def candidates(self) -> dict[str, Candidate]:
        """Return a dict of candidates for the current environment."""
        result: dict[str, Candidate] = {}
        for candidates in self.all_candidates.values():
            for can in candidates:
                if can.req.marker and not can.req.marker.matches(self.env_spec):
                    continue
                result[can.identify()] = can
        return result

    def _read_lockfile(self, lockfile: Mapping[str, Any]) -> None:
        from pdm.project.lockfile import FLAG_CROSS_PLATFORM, FLAG_STATIC_URLS

        root = self.environment.project.root
        static_urls = FLAG_STATIC_URLS in self.environment.project.lockfile.strategy
        self.targets = [EnvSpec.from_spec(**t) for t in lockfile.get("metadata", {}).get("targets", [])]
        if not self.targets and lockfile:  # pragma: no cover
            # XXX: for reading old lockfiles, to be removed in the future
            if FLAG_CROSS_PLATFORM in self.environment.project.lockfile.strategy:
                self.targets.append(self.environment.allow_all_spec)
            else:
                self.targets.append(self.environment.spec)
        with cd(root):
            for package in lockfile.get("package", []):
                version = package.get("version")
                if version:
                    package["version"] = f"=={version}"
                package_name = package.pop("name")
                req_dict = {
                    k: v
                    for k, v in package.items()
                    if k not in ("dependencies", "requires_python", "summary", "files", "targets")
                }
                req = Requirement.from_req_dict(package_name, req_dict)
                if req.is_file_or_url and req.path and not req.url:  # type: ignore[attr-defined]
                    req.url = path_to_url(posixpath.join(root, req.path))  # type: ignore[attr-defined]
                can = Candidate(req, name=package_name, version=version)
                can.hashes = package.get("files", [])
                if not static_urls and any("url" in f for f in can.hashes):
                    raise PdmException(
                        "Static URLs are not allowed in lockfile unless enabled by `pdm lock --static-urls`."
                    )
                can_id = self._identify_candidate(can)
                can.requires_python = package.get("requires_python", "")
                entry = PackageEntry(
                    can,
                    package.get("dependencies", []),
                    package.get("summary", ""),
                )
                self.packages[can_id] = entry

    def _identify_candidate(self, candidate: Candidate) -> CandidateKey:
        url: str | None = None
        if not candidate.req.is_named and candidate.link is not None:
            url = candidate.link.url_without_fragment
            url = self.environment.project.backend.expand_line(cast(str, url))
            if url.startswith("file://"):
                path = posixpath.normpath(url_to_path(url))
                url = path_to_url(path)
        return (
            candidate.identify(),
            candidate.version if not url else None,
            url,
            candidate.req.editable,
        )

    def _get_dependencies_from_lockfile(self, candidate: Candidate) -> CandidateMetadata:
        err = (
            f"Missing package {candidate.identify()} from the lockfile, "
            "the lockfile may be broken. Run `pdm lock --update-reuse` to fix it."
        )
        try:
            entry = self.packages[self._identify_candidate(candidate)]
        except KeyError as e:  # pragma: no cover
            raise CandidateNotFound(err) from e

        deps: list[Requirement] = []
        for line in entry.dependencies:
            deps.append(parse_line(line))
        return CandidateMetadata(deps, candidate.requires_python, entry.summary)

    def dependency_generators(self) -> Iterable[Callable[[Candidate], CandidateMetadata]]:
        return (
            self._get_dependencies_from_local_package,
            self._get_dependencies_from_lockfile,
        )

    def _matching_entries(self, requirement: Requirement) -> Iterable[PackageEntry]:
        from pdm.models.requirements import FileRequirement

        for key, entry in self.packages.items():
            can_req = entry.candidate.req
            if requirement.name:
                if key[0] != requirement.identify():
                    continue
            else:
                assert isinstance(requirement, FileRequirement)
                if not isinstance(can_req, FileRequirement):
                    continue
                if requirement.path and can_req.path:
                    if requirement.path != can_req.path:
                        continue
                elif key[2] is not None and key[2] != url_without_fragments(requirement.url):
                    continue

            yield entry

    def find_candidates(
        self,
        requirement: Requirement,
        allow_prereleases: bool | None = None,
        ignore_requires_python: bool = False,
        minimal_version: bool = False,
    ) -> Iterable[Candidate]:
        if self.is_this_package(requirement):
            candidate = self.make_this_candidate(requirement)
            if candidate is not None:
                yield candidate
                return
        for entry in self._matching_entries(requirement):
            can = entry.candidate.copy_with(requirement)
            if not requirement.name:
                # make sure can.identify() won't return a randomly-generated name
                requirement.name = can.name
            yield can

    def get_hashes(self, candidate: Candidate) -> list[FileHash]:
        return candidate.hashes

    def evaluate_candidates(self, groups: Collection[str]) -> dict[str, Candidate]:
        all_candidates = self.candidates
        result: dict[str, Candidate] = {}
        for key, can in all_candidates.items():
            if not any(g in can.req.groups for g in groups):
                continue
            result[key] = can
        return result

    def merge_result(
        self,
        env_spec: EnvSpec,
        result: Iterable[Candidate],
        fetched_dependencies: dict[tuple[str, str | None], list[Requirement]],
    ) -> None:
        project = self.environment.project
        backend = project.backend
        if env_spec not in self.targets:
            self.targets.append(env_spec)
        for candidate in result:
            key = self._identify_candidate(candidate)
            existing = self.packages.get(key)
            if existing is None:
                deps: list[str] = []
                for r in fetched_dependencies[candidate.dep_key]:
                    # Try to convert to relative paths to make it portable
                    if isinstance(r, FileRequirement) and r.path:
                        try:
                            if r.path.is_absolute():
                                r.path = Path(os.path.normpath(r.path)).relative_to(os.path.normpath(project.root))
                        except ValueError:
                            pass
                        else:
                            r.url = backend.relative_path_to_url(r.path.as_posix())
                    deps.append(r.as_line())
                self.packages[key] = PackageEntry(candidate, deps, candidate.summary)
            else:
                # merge markers
                old_marker = existing.candidate.req.marker
                if old_marker is None or candidate.req.marker is None:
                    new_marker = None
                else:
                    new_marker = old_marker | candidate.req.marker
                    bare_marker, py_spec = new_marker.split_pyspec()
                    if py_spec.is_superset(self.environment.python_requires):
                        new_marker = bare_marker
                    if new_marker.is_any():
                        new_marker = None
                # merge groups
                new_groups = list(set(existing.candidate.req.groups) | set(candidate.req.groups))
                existing.candidate.req = dataclasses.replace(
                    existing.candidate.req, marker=new_marker, groups=new_groups
                )
                # merge file hashes
                for file in candidate.hashes:
                    if file not in existing.candidate.hashes:
                        existing.candidate.hashes.append(file)
        # clear caches
        if "all_candidates" in self.__dict__:
            del self.__dict__["all_candidates"]

    def format_lockfile(self, groups: Iterable[str] | None, strategy: set[str]) -> TOMLDocument:
        """Format lock file from a dict of resolved candidates, a mapping of dependencies
        and a collection of package summaries.
        """
        import tomlkit

        from pdm.formats.base import make_array, make_inline_table
        from pdm.project.lockfile import FLAG_CROSS_PLATFORM, FLAG_INHERIT_METADATA, FLAG_STATIC_URLS

        def _group_sort_key(group: str) -> tuple[bool, str]:
            return group != "default", group

        project = self.environment.project
        packages = tomlkit.aot()
        for entry in sorted(self.packages.values(), key=lambda x: x.candidate.identify()):
            base = tomlkit.table()
            base.update(entry.candidate.as_lockfile_entry(project.root))
            base.add("summary", entry.summary or "")
            if FLAG_INHERIT_METADATA in strategy:
                base.add("groups", sorted(entry.candidate.req.groups, key=_group_sort_key))
                if entry.candidate.req.marker is not None:
                    base.add("marker", str(entry.candidate.req.marker))
            if len(entry.dependencies) > 0:
                base.add("dependencies", make_array(sorted(entry.dependencies), True))
            if hashes := entry.candidate.hashes:
                collected = {}
                for item in hashes:
                    if FLAG_STATIC_URLS in strategy:
                        row = {"url": item["url"], "hash": item["hash"]}
                    else:
                        row = {"file": item["file"], "hash": item["hash"]}
                    inline = make_inline_table(row)
                    # deduplicate and sort
                    collected[tuple(row.values())] = inline
                if collected:
                    base.add("files", make_array([collected[k] for k in sorted(collected)], True))
            packages.append(base)
        doc = tomlkit.document()
        metadata = tomlkit.table()
        if groups is None:
            groups = list(project.iter_groups())
        metadata.update(
            {
                "groups": sorted(groups, key=_group_sort_key),
                "strategy": sorted(strategy),
                "targets": [t.as_dict() for t in self.targets],
            }
        )
        metadata.pop(FLAG_STATIC_URLS, None)
        metadata.pop(FLAG_CROSS_PLATFORM, None)
        doc.add("metadata", metadata)
        doc.add("package", packages)
        return doc
