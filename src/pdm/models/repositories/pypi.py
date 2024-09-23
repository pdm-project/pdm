from __future__ import annotations

from typing import TYPE_CHECKING, cast

from pdm.exceptions import CandidateInfoNotFound, CandidateNotFound
from pdm.models.candidates import Candidate
from pdm.models.repositories.base import BaseRepository, CandidateMetadata, cache_result
from pdm.models.requirements import Requirement, filter_requirements_with_extras
from pdm.models.search import SearchResultParser

if TYPE_CHECKING:
    from typing import Callable, Iterable

    from pdm._types import SearchResults


class PyPIRepository(BaseRepository):
    """Get package and metadata from PyPI source."""

    DEFAULT_INDEX_URL = "https://pypi.org"

    @cache_result
    def _get_dependencies_from_json(self, candidate: Candidate) -> CandidateMetadata:  # pragma: no cover
        if not candidate.name or not candidate.version:
            # Only look for json api for named requirements.
            raise CandidateInfoNotFound(candidate)
        sources = self.get_filtered_sources(candidate.req)
        url_prefixes = [
            proc_url[:-7]  # Strip "/simple".
            for proc_url in (raw_url.rstrip("/") for raw_url in (source.url for source in sources) if raw_url)
            if proc_url.endswith("/simple")
        ]
        session = self.environment.session
        for prefix in url_prefixes:
            json_url = f"{prefix}/pypi/{candidate.name}/{candidate.version}/json"
            resp = session.get(json_url)
            if resp.is_error:
                continue

            info = resp.json()["info"]

            requires_python = info["requires_python"] or ""
            summary = info["summary"] or ""
            try:
                requirement_lines = info["requires_dist"] or []
            except KeyError:
                requirement_lines = info["requires"] or []
            requirements = filter_requirements_with_extras(requirement_lines, candidate.req.extras or ())
            return CandidateMetadata(requirements, requires_python, summary)
        raise CandidateInfoNotFound(candidate)

    def dependency_generators(self) -> Iterable[Callable[[Candidate], CandidateMetadata]]:
        yield self._get_dependencies_from_cache
        if self.find_dependencies_from_local:
            yield self._get_dependencies_from_local_package
        if self.environment.project.config["pypi.json_api"]:
            yield self._get_dependencies_from_json
        yield self._get_dependencies_from_metadata

    def _find_candidates(self, requirement: Requirement, minimal_version: bool) -> Iterable[Candidate]:
        from unearth.utils import LazySequence

        sources = self.get_filtered_sources(requirement)
        req_name = cast(str, requirement.project_name)
        with self.environment.get_finder(sources, env_spec=self.env_spec, minimal_version=minimal_version) as finder:
            cans = LazySequence(
                Candidate.from_installation_candidate(c, requirement)
                for c in finder.find_all_packages(req_name, allow_yanked=requirement.is_pinned)
            )
        if not cans:
            raise CandidateNotFound(
                f"Unable to find candidates for {req_name}. There may "
                "exist some issues with the package name or network condition."
            )
        return cans

    def search(self, query: str) -> SearchResults:
        pypi_simple = self.sources[0].url.rstrip("/")  # type: ignore[union-attr]

        if pypi_simple.endswith("/simple"):
            search_url = pypi_simple[:-6] + "search"
        else:
            search_url = pypi_simple + "/search"

        session = self.environment.session
        resp = session.get(search_url, params={"q": query})
        if resp.status_code == 404:  # pragma: no cover
            self.environment.project.core.ui.warn(
                f"{pypi_simple!r} doesn't support '/search' endpoint, fallback "
                f"to {self.DEFAULT_INDEX_URL!r} now.\n"
                "This may take longer depending on your network condition.",
            )
            resp = session.get(f"{self.DEFAULT_INDEX_URL}/search", params={"q": query})
        parser = SearchResultParser()
        resp.raise_for_status()
        parser.feed(resp.text)
        return parser.results
