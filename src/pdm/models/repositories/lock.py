from __future__ import annotations

import posixpath
from functools import cached_property
from typing import TYPE_CHECKING, Collection, NamedTuple, cast

from pdm.exceptions import CandidateNotFound, PdmException
from pdm.models.candidates import Candidate
from pdm.models.markers import EnvSpec
from pdm.models.repositories.base import BaseRepository, CandidateMetadata
from pdm.models.requirements import Requirement, parse_requirement
from pdm.models.specifiers import PySpecSet
from pdm.utils import cd, path_to_url, url_to_path, url_without_fragments

if TYPE_CHECKING:
    from typing import Any, Callable, Iterable, Mapping

    from pdm._types import FileHash, RepositoryConfig, Target
    from pdm.environments import BaseEnvironment

    CandidateKey = tuple[str, str | None, str | None, bool]


class PackageEntry(NamedTuple):
    candidate: Candidate
    dependencies: list[str]
    requires_python: str
    summary: str
    targets: list[Target]


class LockedRepository(BaseRepository):
    def __init__(
        self,
        lockfile: Mapping[str, Any],
        sources: list[RepositoryConfig],
        environment: BaseEnvironment,
        env_spec: EnvSpec | None = None,
    ) -> None:
        super().__init__(sources, environment, ignore_compatibility=False, env_spec=env_spec)
        self.packages: dict[CandidateKey, PackageEntry] = {}
        self._read_lockfile(lockfile)

    @cached_property
    def all_candidates(self) -> dict[str, Candidate]:
        result: dict[str, Candidate] = {}
        spec = self.env_spec
        for entry in self.packages.values():
            if entry.targets:
                if not any(spec.matches_target(t) for t in entry.targets):
                    continue
            if (marker := entry.candidate.req.marker) is not None:
                if not marker.matches(spec):
                    continue
            result[entry.candidate.identify()] = entry.candidate
        return result

    def _read_lockfile(self, lockfile: Mapping[str, Any]) -> None:
        from pdm.project.lockfile import FLAG_STATIC_URLS

        root = self.environment.project.root
        static_urls = FLAG_STATIC_URLS in self.environment.project.lockfile.strategy
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
                entry = PackageEntry(
                    can,
                    package.get("dependencies", []),
                    package.get("requires_python", ""),
                    package.get("summary", ""),
                    package.get("targets", []),
                )
                self.packages[can_id] = entry

    def _identify_candidate(self, candidate: Candidate) -> CandidateKey:
        url: str | None = None
        if candidate.link is not None:
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
            if line.startswith("-e "):
                deps.append(parse_requirement(line[3:], True))
            else:
                deps.append(parse_requirement(line))
        return CandidateMetadata(deps, entry.requires_python, entry.summary)

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
            if not PySpecSet(entry.requires_python).contains(str(self.environment.interpreter.version), True):
                continue
            can = entry.candidate.copy_with(requirement)
            can.requires_python = entry.requires_python
            if not requirement.name:
                # make sure can.identify() won't return a randomly-generated name
                requirement.name = can.name
            yield can

    def get_hashes(self, candidate: Candidate) -> list[FileHash]:
        return candidate.hashes

    def evaluate_candidates(self, groups: Collection[str]) -> Iterable[Candidate]:
        candidates = self.all_candidates
        for can in candidates.values():
            if not any(g in can.req.groups for g in groups):
                continue
            yield can
