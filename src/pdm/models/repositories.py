from __future__ import annotations

import dataclasses
import posixpath
import sys
from functools import lru_cache, wraps
from typing import TYPE_CHECKING, Any, Callable, Iterable, Mapping, TypeVar, cast

from unearth import Link

from pdm import termui
from pdm.exceptions import CandidateInfoNotFound, CandidateNotFound
from pdm.models.candidates import Candidate, make_candidate
from pdm.models.requirements import (
    Requirement,
    filter_requirements_with_extras,
    parse_requirement,
)
from pdm.models.search import SearchResultParser
from pdm.models.specifiers import PySpecSet
from pdm.utils import (
    cd,
    normalize_name,
    path_to_url,
    url_to_path,
    url_without_fragments,
)

if TYPE_CHECKING:
    from pdm._types import CandidateInfo, SearchResult, Source
    from pdm.models.environment import Environment

ALLOW_ALL_PYTHON = PySpecSet()
T = TypeVar("T", bound="BaseRepository")


def cache_result(func: Callable[[T, Candidate], CandidateInfo]) -> Callable[[T, Candidate], CandidateInfo]:
    @wraps(func)
    def wrapper(self: T, candidate: Candidate) -> CandidateInfo:
        result = func(self, candidate)
        prepared = candidate.prepared
        if prepared and prepared.should_cache():
            self._candidate_info_cache.set(candidate, result)
        return result

    return wrapper


class BaseRepository:
    """A Repository acts as the source of packages and metadata."""

    def __init__(
        self,
        sources: list[Source],
        environment: Environment,
        ignore_compatibility: bool = True,
    ) -> None:
        """
        :param sources: a list of sources to download packages from.
        :param environment: the bound environment instance.
        :param ignore_compatibility: if True, don't evaluate candidate against
            the current environment.
        """
        self.sources = sources
        self.environment = environment
        self.ignore_compatibility = ignore_compatibility
        self._candidate_info_cache = environment.project.make_candidate_info_cache()
        self._hash_cache = environment.project.make_hash_cache()

    def get_filtered_sources(self, req: Requirement) -> list[Source]:
        """Get matching sources based on the index attribute."""
        return self.sources

    def get_dependencies(self, candidate: Candidate) -> tuple[list[Requirement], PySpecSet, str]:
        """Get (dependencies, python_specifier, summary) of the candidate."""
        requires_python, summary = "", ""
        requirements: list[str] = []
        last_ext_info = None
        for getter in self.dependency_generators():
            try:
                requirements, requires_python, summary = getter(candidate)
            except CandidateInfoNotFound:
                last_ext_info = sys.exc_info()
                continue
            break
        else:
            if last_ext_info is not None:
                raise last_ext_info[1].with_traceback(last_ext_info[2])  # type: ignore[union-attr]
        reqs: list[Requirement] = []
        for line in requirements:
            if line.startswith("-e "):
                reqs.append(parse_requirement(line[3:], True))
            else:
                reqs.append(parse_requirement(line))
        if candidate.req.extras:
            # XXX: If the requirement has extras, add the original candidate
            # (without extras) as its dependency. This ensures the same package with
            # different extras resolve to the same version.
            self_req = dataclasses.replace(
                candidate.req.as_pinned_version(candidate.version),
                extras=None,
                marker=None,
            )
            reqs.append(self_req)
        # Store the metadata on the candidate for caching
        candidate.requires_python = requires_python
        candidate.summary = summary
        if not self.ignore_compatibility:
            pep508_env = self.environment.marker_environment
            reqs = [req for req in reqs if not req.marker or req.marker.evaluate(pep508_env)]
        return reqs, PySpecSet(requires_python), summary

    def _find_candidates(self, requirement: Requirement) -> Iterable[Candidate]:
        raise NotImplementedError

    def is_this_package(self, requirement: Requirement) -> bool:
        """Whether the requirement is the same as this package"""
        project = self.environment.project
        return requirement.is_named and project.name is not None and requirement.key == normalize_name(project.name)

    def make_this_candidate(self, requirement: Requirement) -> Candidate:
        """Make a candidate for this package.
        In this case the finder will look for a candidate from the package sources
        """
        project = self.environment.project
        assert project.name
        link = Link.from_path(project.root)
        candidate = make_candidate(requirement, project.name, link=link)
        candidate.prepare(self.environment).metadata
        return candidate

    def find_candidates(
        self,
        requirement: Requirement,
        allow_prereleases: bool | None = None,
        ignore_requires_python: bool = False,
    ) -> Iterable[Candidate]:
        """Find candidates of the given NamedRequirement. Let it to be implemented in
        subclasses.
        """
        # `allow_prereleases` is None means leave it to specifier to decide whether to
        # include prereleases

        if self.is_this_package(requirement):
            return [self.make_this_candidate(requirement)]
        requires_python = requirement.requires_python & self.environment.python_requires
        cans = list(self._find_candidates(requirement))
        applicable_cans = [
            c
            for c in cans
            if requirement.specifier.contains(c.version, allow_prereleases)  # type: ignore[arg-type, union-attr]
        ]

        applicable_cans_python_compatible = [
            c for c in applicable_cans if ignore_requires_python or requires_python.is_subset(c.requires_python)
        ]
        # Evaluate data-requires-python attr and discard incompatible candidates
        # to reduce the number of candidates to resolve.
        if applicable_cans_python_compatible:
            applicable_cans = applicable_cans_python_compatible

        if not applicable_cans:
            termui.logger.debug("\tCould not find any matching candidates.")

        if not applicable_cans and allow_prereleases is None:
            # No non-pre-releases is found, force pre-releases now
            applicable_cans = [
                c for c in cans if requirement.specifier.contains(c.version, True)  # type: ignore[arg-type, union-attr]
            ]
            applicable_cans_python_compatible = [
                c for c in applicable_cans if ignore_requires_python or requires_python.is_subset(c.requires_python)
            ]
            if applicable_cans_python_compatible:
                applicable_cans = applicable_cans_python_compatible

            if not applicable_cans:
                termui.logger.debug(
                    "\tCould not find any matching candidates even when considering pre-releases.",
                )

        def print_candidates(title: str, candidates: list[Candidate], max_lines: int = 10) -> None:
            termui.logger.debug("\t" + title)
            logged_lines = set()
            for can in candidates:
                new_line = f"\t  {can!r}"
                if new_line not in logged_lines:
                    logged_lines.add(new_line)
                    if len(logged_lines) > max_lines:
                        termui.logger.debug(f"\t  ... [{len(candidates)-max_lines} more candidate(s)]")
                        break
                    else:
                        termui.logger.debug(new_line)

        if applicable_cans:
            print_candidates("Found matching candidates:", applicable_cans)
        elif cans:
            print_candidates("Found but non-matching candidates:", cans)

        return applicable_cans

    def _get_dependencies_from_cache(self, candidate: Candidate) -> CandidateInfo:
        try:
            result = self._candidate_info_cache.get(candidate)
        except KeyError:
            raise CandidateInfoNotFound(candidate) from None
        return result

    @cache_result
    def _get_dependencies_from_metadata(self, candidate: Candidate) -> CandidateInfo:
        prepared = candidate.prepare(self.environment)
        deps = prepared.get_dependencies_from_metadata()
        requires_python = candidate.requires_python
        summary = prepared.metadata.metadata["Summary"]
        return deps, requires_python, summary

    def get_hashes(self, candidate: Candidate) -> dict[Link, str] | None:
        """Get hashes of all possible installable candidates
        of a given package version.
        """
        if (
            candidate.req.is_vcs
            or candidate.req.is_file_or_url
            and candidate.req.is_local_dir  # type: ignore[attr-defined]
        ):
            return None
        if candidate.hashes:
            return candidate.hashes
        req = candidate.req.as_pinned_version(candidate.version)
        if candidate.req.is_file_or_url:
            matching_candidates: Iterable[Candidate] = [candidate]
        else:
            matching_candidates = self.find_candidates(req, ignore_requires_python=True)
        result: dict[str, str] = {}
        with self.environment.get_finder(self.sources) as finder:
            for c in matching_candidates:
                assert c.link is not None
                # Prepare the candidate to replace vars in the link URL
                prepared_link = c.prepare(self.environment).link
                if (
                    not prepared_link
                    or prepared_link.is_vcs
                    or prepared_link.is_file
                    and prepared_link.file_path.is_dir()
                ):
                    continue
                result[c.link] = self._hash_cache.get_hash(prepared_link, finder.session)
        return result or None

    def dependency_generators(self) -> Iterable[Callable[[Candidate], CandidateInfo]]:
        """Return an iterable of getter functions to get dependencies, which will be
        called one by one.
        """
        raise NotImplementedError

    def search(self, query: str) -> SearchResult:
        """Search package by name or summary.

        :param query: query string
        :returns: search result, a dictionary of name: package metadata
        """
        raise NotImplementedError


class PyPIRepository(BaseRepository):
    """Get package and metadata from PyPI source."""

    DEFAULT_INDEX_URL = "https://pypi.org"

    @cache_result
    def _get_dependencies_from_json(self, candidate: Candidate) -> CandidateInfo:
        if not candidate.name or not candidate.version:
            # Only look for json api for named requirements.
            raise CandidateInfoNotFound(candidate)
        sources = self.get_filtered_sources(candidate.req)
        url_prefixes = [
            proc_url[:-7]  # Strip "/simple".
            for proc_url in (raw_url.rstrip("/") for raw_url in (source.get("url", "") for source in sources))
            if proc_url.endswith("/simple")
        ]
        with self.environment.get_finder(sources) as finder:
            session = finder.session
            for prefix in url_prefixes:
                json_url = f"{prefix}/pypi/{candidate.name}/{candidate.version}/json"
                resp = session.get(json_url)
                if not resp.ok:
                    continue

                info = resp.json()["info"]

                requires_python = info["requires_python"] or ""
                summary = info["summary"] or ""
                try:
                    requirement_lines = info["requires_dist"] or []
                except KeyError:
                    requirement_lines = info["requires"] or []
                requirements = filter_requirements_with_extras(
                    cast(str, candidate.req.project_name),
                    requirement_lines,
                    candidate.req.extras or (),
                )
                return requirements, requires_python, summary
        raise CandidateInfoNotFound(candidate)

    def dependency_generators(self) -> Iterable[Callable[[Candidate], CandidateInfo]]:
        yield self._get_dependencies_from_cache
        if self.environment.project.config["pypi.json_api"]:
            yield self._get_dependencies_from_json
        yield self._get_dependencies_from_metadata

    @lru_cache()
    def _find_candidates(self, requirement: Requirement) -> Iterable[Candidate]:
        sources = self.get_filtered_sources(requirement)
        with self.environment.get_finder(sources, self.ignore_compatibility) as finder:
            cans = [
                Candidate.from_installation_candidate(c, requirement)
                for c in finder.find_all_packages(requirement.project_name, allow_yanked=requirement.is_pinned)
            ]
        if not cans:
            raise CandidateNotFound(
                f"Unable to find candidates for {requirement.project_name}. There may "
                "exist some issues with the package name or network condition."
            )
        return cans

    def search(self, query: str) -> SearchResult:
        pypi_simple = self.sources[0]["url"].rstrip("/")

        if pypi_simple.endswith("/simple"):
            search_url = pypi_simple[:-6] + "search"
        else:
            search_url = pypi_simple + "/search"

        with self.environment.get_finder() as finder:
            session = finder.session
            resp = session.get(search_url, params={"q": query})
            if resp.status_code == 404:
                self.environment.project.core.ui.echo(
                    f"{pypi_simple!r} doesn't support '/search' endpoint, fallback "
                    f"to {self.DEFAULT_INDEX_URL!r} now.\n"
                    "This may take longer depending on your network condition.",
                    err=True,
                    style="warning",
                )
                resp = session.get(f"{self.DEFAULT_INDEX_URL}/search", params={"q": query})
            parser = SearchResultParser()
            resp.raise_for_status()
            parser.feed(resp.text)
            return parser.results


class LockedRepository(BaseRepository):
    def __init__(
        self,
        lockfile: Mapping[str, Any],
        sources: list[Source],
        environment: Environment,
    ) -> None:
        super().__init__(sources, environment, ignore_compatibility=False)
        self.packages: dict[tuple, Candidate] = {}
        self.file_hashes: dict[tuple[str, str], dict[Link, str]] = {}
        self.candidate_info: dict[tuple, CandidateInfo] = {}
        self._read_lockfile(lockfile)

    @property
    def all_candidates(self) -> dict[str, Candidate]:
        return {can.req.identify(): can for can in self.packages.values()}

    def _read_lockfile(self, lockfile: Mapping[str, Any]) -> None:
        root = self.environment.project.root
        with cd(root):
            for package in lockfile.get("package", []):
                version = package.get("version")
                if version:
                    package["version"] = f"=={version}"
                package_name = package.pop("name")
                req_dict = {k: v for k, v in package.items() if k not in ("dependencies", "requires_python", "summary")}
                req = Requirement.from_req_dict(package_name, req_dict)
                if req.is_file_or_url and req.path and not req.url:  # type: ignore[attr-defined]
                    req.url = path_to_url(posixpath.join(root, req.path))  # type: ignore[attr-defined]
                can = make_candidate(req, name=package_name, version=version)
                can_id = self._identify_candidate(can)
                self.packages[can_id] = can
                candidate_info: CandidateInfo = (
                    package.get("dependencies", []),
                    package.get("requires_python", ""),
                    package.get("summary", ""),
                )
                self.candidate_info[can_id] = candidate_info

        for key, hashes in lockfile.get("metadata", {}).get("files", {}).items():
            self.file_hashes[tuple(key.split(None, 1))] = {  # type: ignore[index]
                Link(item["url"]): item["hash"] for item in hashes if "url" in item
            }

    def _identify_candidate(self, candidate: Candidate) -> tuple:
        url = getattr(candidate.req, "url", None)
        if url is not None:
            url = url_without_fragments(url)
            url = self.environment.project.backend.expand_line(url)
            if url.startswith("file://"):
                path = posixpath.normpath(url_to_path(url))
                url = path_to_url(path)
        return (
            candidate.identify(),
            candidate.version if not url else None,
            url,
            candidate.req.editable,
        )

    def _get_dependencies_from_lockfile(self, candidate: Candidate) -> CandidateInfo:
        return self.candidate_info[self._identify_candidate(candidate)]

    def _get_dependency_from_local_package(self, candidate: Candidate) -> CandidateInfo:
        """Adds the local package as a candidate only if the candidate
        name is the same as the local package."""
        if candidate.name != self.environment.project.name:
            raise CandidateInfoNotFound(candidate) from None

        reqs = self.environment.project.pyproject.metadata.get("dependencies", [])
        optional_dependencies = self.environment.project.pyproject.metadata.get("optional-dependencies", {})
        if candidate.req.extras is not None:
            reqs = sum(
                (optional_dependencies.get(g, []) for g in candidate.req.extras),
                [],
            )

        return (
            reqs,
            str(self.environment.python_requires),
            self.environment.project.pyproject.metadata.get("description", "UNKNOWN"),
        )

    def dependency_generators(self) -> Iterable[Callable[[Candidate], CandidateInfo]]:
        return (
            self._get_dependency_from_local_package,
            self._get_dependencies_from_lockfile,
        )

    def _matching_keys(self, requirement: Requirement) -> Iterable[tuple]:
        for key in self.candidate_info:
            if requirement.name:
                if key[0] != requirement.identify():
                    continue
            elif key[2] is not None:
                if key[2] != url_without_fragments(getattr(requirement, "url", "")):
                    continue
            else:
                can_req = self.packages[key].req
                if can_req.path != getattr(requirement, "path", None):  # type: ignore[attr-defined]
                    continue

            yield key

    def find_candidates(
        self,
        requirement: Requirement,
        allow_prereleases: bool | None = None,
        ignore_requires_python: bool = False,
    ) -> Iterable[Candidate]:
        if self.is_this_package(requirement):
            candidate = self.make_this_candidate(requirement)
            if candidate is not None:
                yield candidate
                return
        for key in self._matching_keys(requirement):
            info = self.candidate_info[key]
            if not PySpecSet(info[1]).contains(str(self.environment.interpreter.version), True):
                continue
            can = self.packages[key]
            can.requires_python = info[1]
            if not requirement.name:
                # make sure can.identify() won't return a randomly-generated name
                requirement.name = can.name
            can.req = requirement
            yield can

    def get_hashes(self, candidate: Candidate) -> dict[Link, str] | None:
        assert candidate.name
        return self.file_hashes.get((normalize_name(candidate.name), candidate.version or ""))
