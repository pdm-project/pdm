from __future__ import annotations

import dataclasses
import itertools
import posixpath
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Collection, cast

from dep_logic.markers import AnyMarker, BaseMarker

from pdm.exceptions import CandidateNotFound, PdmException
from pdm.models.candidates import Candidate
from pdm.models.markers import EnvSpec, exclude_multi, get_marker
from pdm.models.repositories.base import BaseRepository, CandidateMetadata
from pdm.models.requirements import FileRequirement, Requirement, parse_line
from pdm.utils import cd, url_to_path, url_without_fragments

if TYPE_CHECKING:
    from typing import Any, Callable, Iterable, Mapping

    from pdm._types import FileHash, RepositoryConfig
    from pdm.environments import BaseEnvironment

    CandidateKey = tuple[str, str | None, str | None, bool]


@dataclasses.dataclass(frozen=True)
class Package:
    candidate: Candidate
    dependencies: list[str] | None = None
    summary: str = ""
    marker: BaseMarker = dataclasses.field(default_factory=AnyMarker)


class LockedRepository(BaseRepository):
    def __init__(
        self,
        lockfile: Mapping[str, Any],
        sources: list[RepositoryConfig],
        environment: BaseEnvironment,
        env_spec: EnvSpec | None = None,
    ) -> None:
        super().__init__(sources, environment, env_spec=env_spec or environment.spec)
        self.packages: dict[CandidateKey, Package] = {}
        self.targets: list[EnvSpec] = []
        self._read_lockfile(lockfile)

    def add_package(self, package: Package) -> None:
        self.packages[self._identify_candidate(package.candidate)] = package

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
                if can.req.marker:
                    marker = exclude_multi(can.req.marker, "extras", "dependency_groups")
                    if not marker.matches(self.env_spec):
                        continue
                result[can.identify()] = can
        return result

    def _read_lockfile(self, lockfile: Mapping[str, Any]) -> None:
        if lockfile.get("lock-version"):
            return self._read_pylock(lockfile)
        else:
            return self._read_pdm_lock(lockfile)

    def _read_pylock(self, lockfile: Mapping[str, Any]) -> None:
        root = self.environment.project.root

        if "targets" in lockfile.get("tool", {}).get("pdm", {}):
            self.targets = [EnvSpec.from_spec(**t) for t in lockfile["tool"]["pdm"]["targets"]]
        else:
            for marker in lockfile.get("environments", []):  # pragma: no cover
                self.targets.append(EnvSpec.from_marker(get_marker(cast(str, marker))))

        with cd(root):
            for package in lockfile.get("packages", []):
                group_marker = AnyMarker()
                package_name = package.pop("name")
                req_dict: dict[str, str | bool] = {}
                if "version" in package:
                    req_dict["version"] = f"=={package['version']}"
                if "marker" in package:
                    package_marker = get_marker(cast(str, package["marker"]))
                    req_marker = exclude_multi(package_marker, "extras", "dependency_groups")
                    group_marker = package_marker.inner.only("extras", "dependency_groups")
                    if not req_marker.is_any():
                        req_dict["marker"] = str(req_marker)
                if vcs := package.get("vcs"):  # pragma: no cover
                    req_dict[vcs["type"]] = vcs["url"]
                    req_dict["ref"] = vcs.get("requested-revision")
                    req_dict["revision"] = vcs.get("commit-id")
                    req_dict["subdirectory"] = vcs.get("subdirectory")
                elif directory := package.get("directory"):  # pragma: no cover
                    req_dict["path"] = directory["path"]
                    req_dict["editable"] = directory.get("editable", False)
                    req_dict["subdirectory"] = directory.get("subdirectory")
                elif archive := package.get("archive"):  # pragma: no cover
                    req_dict["url"] = archive.get("url")
                    req_dict["path"] = archive.get("path")
                    req_dict["subdirectory"] = archive.get("subdirectory")
                req = Requirement.from_req_dict(package_name, req_dict)
                if req.is_file_or_url and req.path and not req.url:  # type: ignore[attr-defined]
                    req.url = root.joinpath(req.path).as_uri()  # type: ignore[attr-defined]
                candidate = Candidate(req=req, name=package_name, version=package.get("version"))
                candidate.requires_python = package.get("requires-python", "")
                for artifact in itertools.chain(
                    package.get("wheels", []), [sdist] if (sdist := package.get("sdist")) else []
                ):
                    algo, hash_value = next(iter(artifact["hashes"].items()))
                    hash_item: FileHash = {"hash": f"{algo}:{hash_value}"}
                    if "url" in artifact:
                        hash_item["url"] = artifact["url"]
                    if "name" in artifact:
                        hash_item["file"] = artifact["name"]
                    candidate.hashes.append(hash_item)
                dependencies = package.get("tool", {}).get("pdm", {}).get("dependencies")
                self.packages[self._identify_candidate(candidate)] = Package(candidate, dependencies, "", group_marker)

    def _read_pdm_lock(self, lockfile: Mapping[str, Any]) -> None:
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
                    req.url = root.joinpath(req.path).as_uri()  # type: ignore[attr-defined]
                can = Candidate(req, name=package_name, version=version)
                can.hashes = package.get("files", [])
                if not static_urls and any("url" in f for f in can.hashes):
                    raise PdmException(
                        "Static URLs are not allowed in lockfile unless enabled by `pdm lock --static-urls`."
                    )
                can_id = self._identify_candidate(can)
                can.requires_python = package.get("requires_python", "")
                entry = Package(
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
                url = Path(path).as_uri()
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

        if entry.dependencies is None:
            raise CandidateNotFound(f"Missing dependencies from the lockfile for package {candidate.identify()}")
        # populate candidate metadata
        if not candidate.name:
            candidate.name = entry.candidate.name
        if not candidate.version:
            candidate.version = entry.candidate.version
        if not candidate.requires_python:
            candidate.requires_python = entry.candidate.requires_python
        deps: list[Requirement] = []
        for line in entry.dependencies:
            deps.append(parse_line(line))
        return CandidateMetadata(deps, candidate.requires_python, entry.summary)

    def dependency_generators(self) -> Iterable[Callable[[Candidate], CandidateMetadata]]:
        return (self._get_dependencies_from_lockfile,)

    def _matching_entries(self, requirement: Requirement) -> Iterable[Package]:
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

    def evaluate_candidates(self, groups: Collection[str], evaluate_markers: bool = True) -> Iterable[Package]:
        extras, dependency_groups = self.environment.project.split_extras_groups(list(groups))
        for package in self.packages.values():
            can = package.candidate
            if evaluate_markers and can.req.marker and not can.req.marker.matches(self.env_spec):
                continue
            if not package.marker.evaluate({"extras": set(extras), "dependency_groups": set(dependency_groups)}):
                continue
            if can.req.groups and not any(g in can.req.groups for g in groups):
                continue
            yield package

    def merge_result(self, env_spec: EnvSpec, result: Iterable[Package]) -> None:
        if env_spec not in self.targets:
            self.targets.append(env_spec)
        for entry in result:
            key = self._identify_candidate(entry.candidate)
            existing = self.packages.get(key)
            if existing is None:
                self.packages[key] = entry
            else:
                # merge markers
                old_marker = existing.candidate.req.marker
                if old_marker is None or entry.candidate.req.marker is None:
                    new_marker = None
                else:
                    new_marker = old_marker | entry.candidate.req.marker
                    bare_marker, py_spec = new_marker.split_pyspec()
                    if py_spec.is_superset(self.environment.python_requires):
                        new_marker = bare_marker
                    if new_marker.is_any():
                        new_marker = None
                # merge groups
                new_groups = list(set(existing.candidate.req.groups) | set(entry.candidate.req.groups))
                existing.candidate.req = dataclasses.replace(
                    existing.candidate.req, marker=new_marker, groups=new_groups
                )
                # merge file hashes
                for file in entry.candidate.hashes:
                    if file not in existing.candidate.hashes:
                        existing.candidate.hashes.append(file)
        # clear caches
        if "all_candidates" in self.__dict__:
            del self.__dict__["all_candidates"]
