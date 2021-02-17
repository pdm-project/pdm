from __future__ import annotations

import sys
from functools import lru_cache, wraps
from typing import TYPE_CHECKING, Callable, Dict, Iterable, List, Optional, Tuple

from pip._vendor.html5lib import parse

from pdm._types import CandidateInfo, Package, SearchResult, Source
from pdm.exceptions import CandidateInfoNotFound, CorruptedCacheError
from pdm.iostream import stream
from pdm.models.candidates import Candidate
from pdm.models.requirements import (
    Requirement,
    filter_requirements_with_extras,
    parse_requirement,
)
from pdm.models.specifiers import PySpecSet, SpecifierSet
from pdm.utils import allow_all_wheels

if TYPE_CHECKING:
    from pdm.models.environment import Environment


def cache_result(
    func: Callable[["BaseRepository", Candidate], CandidateInfo]
) -> Callable[["BaseRepository", Candidate], CandidateInfo]:
    @wraps(func)
    def wrapper(self, candidate: Candidate) -> CandidateInfo:
        result = func(self, candidate)
        self._candidate_info_cache.set(candidate, result)
        return result

    return wrapper


class BaseRepository:
    """A Repository acts as the source of packages and metadata."""

    def __init__(self, sources: List[Source], environment: Environment) -> None:
        """
        :param sources: a list of sources to download packages from.
        :param environment: the bound environment instance.
        """
        self.sources = sources
        self.environment = environment
        self._candidate_info_cache = environment.project.make_candidate_info_cache()
        self._hash_cache = environment.project.make_hash_cache()

    def get_filtered_sources(self, req: Requirement) -> List[Source]:
        """Get matching sources based on the index attribute."""
        if not req.index:
            return self.sources
        return [source for source in self.sources if source["name"] == req.index]

    def get_dependencies(
        self, candidate: Candidate
    ) -> Tuple[List[Requirement], PySpecSet, str]:
        """Get (dependencies, python_specifier, summary) of the candidate."""
        requirements, requires_python, summary = [], "", ""
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
                raise last_ext_info[1].with_traceback(last_ext_info[2])
        requirements = [parse_requirement(line) for line in requirements]
        if candidate.req.extras:
            # HACK: If this candidate has extras, add the original candidate
            # (same pinned version, no extras) as its dependency. This ensures
            # the same package with different extras (treated as distinct by
            # the resolver) have the same version.
            self_req = candidate.req.copy()
            self_req.extras = None
            requirements.append(self_req)
        return requirements, PySpecSet(requires_python), summary

    def _find_candidates(self, requirement: Requirement) -> Iterable[Candidate]:
        raise NotImplementedError

    def find_candidates(
        self,
        requirement: Requirement,
        requires_python: PySpecSet = PySpecSet(),
        allow_prereleases: Optional[bool] = None,
        allow_all: bool = False,
    ) -> Iterable[Candidate]:
        """Find candidates of the given NamedRequirement. Let it to be implemented in
        subclasses.
        """
        # `allow_prereleases` is None means leave it to specifier to decide whether to
        # include prereleases
        if allow_prereleases is None:
            allow_prereleases = requirement.allow_prereleases

        requires_python = requires_python & requirement.requires_python
        cans = list(self._find_candidates(requirement))

        sorted_cans = sorted(
            (
                c
                for c in cans
                if requirement.specifier.contains(c.version, allow_prereleases)
                and (allow_all or requires_python.is_subset(c.requires_python))
            ),
            key=lambda c: (c.version, c.link.is_wheel),
            reverse=True,
        )

        if not sorted_cans and allow_prereleases is None:
            # No non-pre-releases is found, force pre-releases now
            sorted_cans = sorted(
                (
                    c
                    for c in cans
                    if requirement.specifier.contains(c.version, True)
                    and (allow_all or requires_python.is_subset(c.requires_python))
                ),
                key=lambda c: c.version,
                reverse=True,
            )
        return sorted_cans

    def _get_dependencies_from_cache(self, candidate: Candidate) -> CandidateInfo:
        try:
            result = self._candidate_info_cache.get(candidate)
        except CorruptedCacheError:
            self._candidate_info_cache.clear()
            raise CandidateInfoNotFound(candidate)
        except KeyError:
            raise CandidateInfoNotFound(candidate)
        return result

    @cache_result
    def _get_dependencies_from_metadata(self, candidate: Candidate) -> CandidateInfo:
        deps = candidate.get_dependencies_from_metadata()
        requires_python = candidate.requires_python
        summary = candidate.metadata.summary
        return deps, requires_python, summary

    def get_hashes(self, candidate: Candidate) -> Optional[Dict[str, str]]:
        """Get hashes of all possible installable candidates
        of a given package version.
        """
        if (
            candidate.req.is_vcs
            or candidate.req.is_file_or_url
            and candidate.req.is_local_dir
        ):
            return
        if candidate.hashes:
            return candidate.hashes
        req = candidate.req.copy()
        req.specifier = SpecifierSet(f"=={candidate.version}")
        matching_candidates = self.find_candidates(req, allow_all=True)
        with self.environment.get_finder(self.sources) as finder:
            self._hash_cache.session = finder.session
            return {
                c.link.filename: self._hash_cache.get_hash(c.link)
                for c in matching_candidates
            }

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
            for proc_url in (
                raw_url.rstrip("/")
                for raw_url in (source.get("url", "") for source in sources)
            )
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
                    requirement_lines, candidate.req.extras or ()
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
        with self.environment.get_finder(sources, True) as finder, allow_all_wheels():
            return [
                Candidate.from_installation_candidate(c, requirement, self.environment)
                for c in finder.find_all_candidates(requirement.project_name)
            ]

    def search(self, query: str) -> SearchResult:
        pypi_simple = self.sources[0]["url"].rstrip("/")
        results = []

        if pypi_simple.endswith("/simple"):
            search_url = pypi_simple[:-6] + "search"
        else:
            search_url = pypi_simple + "/search"

        with self.environment.get_finder() as finder:
            session = finder.session
            resp = session.get(search_url, params={"q": query})
            if resp.status_code == 404:
                stream.echo(
                    stream.yellow(
                        f"{pypi_simple!r} doesn't support '/search' endpoint, fallback "
                        f"to {self.DEFAULT_INDEX_URL!r} now.\n"
                        "This may take longer depending on your network condition."
                    ),
                    err=True,
                )
                resp = session.get(
                    f"{self.DEFAULT_INDEX_URL}/search", params={"q": query}
                )
            resp.raise_for_status()
            content = parse(resp.content, namespaceHTMLElements=False)

        for result in content.findall(".//*[@class='package-snippet']"):
            name = result.find("h3/*[@class='package-snippet__name']").text
            version = result.find("h3/*[@class='package-snippet__version']").text

            if not name or not version:
                continue

            description = result.find("p[@class='package-snippet__description']").text
            if not description:
                description = ""

            result = Package(name, version, description)
            results.append(result)

        return results
