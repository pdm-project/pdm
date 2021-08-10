from __future__ import annotations

import dataclasses
import sys
from functools import lru_cache, wraps
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Tuple,
    TypeVar,
)

from pip._vendor.html5lib import parse
from pkg_resources import parse_version

from pdm import termui
from pdm._types import CandidateInfo, Package, SearchResult, Source
from pdm.exceptions import CandidateInfoNotFound, CandidateNotFound, CorruptedCacheError
from pdm.models.candidates import Candidate
from pdm.models.requirements import (
    Requirement,
    filter_requirements_with_extras,
    parse_requirement,
)
from pdm.models.specifiers import PySpecSet, get_specifier
from pdm.utils import allow_all_wheels, normalize_name, url_without_fragments

if TYPE_CHECKING:
    from pdm.models.environment import Environment

ALLOW_ALL_PYTHON = PySpecSet()
T = TypeVar("T", bound="BaseRepository")


def cache_result(
    func: Callable[[T, Candidate], CandidateInfo]
) -> Callable[[T, Candidate], CandidateInfo]:
    @wraps(func)
    def wrapper(self: T, candidate: Candidate) -> CandidateInfo:
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
        return self.sources

    def get_dependencies(
        self, candidate: Candidate
    ) -> Tuple[List[Requirement], PySpecSet, str]:
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
                raise last_ext_info[1].with_traceback(last_ext_info[2])  # type: ignore
        reqs = [parse_requirement(line) for line in requirements]
        if candidate.req.extras:
            # HACK: If this candidate has extras, add the original candidate
            # (same pinned version, no extras) as its dependency. This ensures
            # the same package with different extras (treated as distinct by
            # the resolver) have the same version.
            self_req = dataclasses.replace(candidate.req, extras=None)
            reqs.append(self_req)
        return reqs, PySpecSet(requires_python), summary

    def _find_candidates(self, requirement: Requirement) -> Iterable[Candidate]:
        raise NotImplementedError

    def find_candidates(
        self,
        requirement: Requirement,
        requires_python: PySpecSet = ALLOW_ALL_PYTHON,
        allow_prereleases: Optional[bool] = None,
        allow_all: bool = False,
    ) -> Iterable[Candidate]:
        """Find candidates of the given NamedRequirement. Let it to be implemented in
        subclasses.
        """
        # `allow_prereleases` is None means leave it to specifier to decide whether to
        # include prereleases
        requires_python = requires_python & requirement.requires_python
        cans = sorted(
            self._find_candidates(requirement),
            key=lambda c: (parse_version(c.version), c.link.is_wheel),  # type: ignore
            reverse=True,
        )
        applicable_cans = [
            c
            for c in cans
            if requirement.specifier.contains(  # type: ignore
                c.version, allow_prereleases  # type: ignore
            )
            and (allow_all or requires_python.is_subset(c.requires_python))
        ]

        if not applicable_cans:
            termui.logger.debug("\tCould not find any matching candidates.")

        if not applicable_cans and allow_prereleases is None:
            # No non-pre-releases is found, force pre-releases now
            applicable_cans = [
                c
                for c in cans
                if requirement.specifier.contains(c.version, True)  # type: ignore
                and (allow_all or requires_python.is_subset(c.requires_python))
            ]

            if not applicable_cans:
                termui.logger.debug(
                    "\tCould not find any matching candidates even when considering "
                    "pre-releases.",
                )

        def print_candidates(
            title: str, candidates: List[Candidate], max_lines: int = 10
        ) -> None:
            termui.logger.debug("\t" + title)
            logged_lines = set()
            for can in candidates:
                new_line = f"\t  {can}"
                if new_line not in logged_lines:
                    logged_lines.add(new_line)
                    if len(logged_lines) > max_lines:
                        termui.logger.debug(
                            f"\t  ... [{len(candidates)-max_lines} more candidate(s)]"
                        )
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
        summary = candidate.metadata.metadata["Summary"]
        return deps, requires_python, summary

    def get_hashes(self, candidate: Candidate) -> Optional[Dict[str, str]]:
        """Get hashes of all possible installable candidates
        of a given package version.
        """
        if (
            candidate.req.is_vcs
            or candidate.req.is_file_or_url
            and candidate.req.is_local_dir  # type: ignore
        ):
            return None
        if candidate.hashes:
            return candidate.hashes
        req = dataclasses.replace(
            candidate.req, specifier=get_specifier(f"=={candidate.version}")
        )
        if candidate.req.is_file_or_url:
            matching_candidates: Iterable[Candidate] = [candidate]
        else:
            matching_candidates = self.find_candidates(req, allow_all=True)
        with self.environment.get_finder(self.sources) as finder:
            self._hash_cache.session = finder.session  # type: ignore
            return {
                c.link.filename: self._hash_cache.get_hash(c.link)  # type: ignore
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
            session = finder.session  # type: ignore
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
            cans = [
                Candidate.from_installation_candidate(c, requirement, self.environment)
                for c in finder.find_all_candidates(requirement.project_name)
            ]
        if not cans:
            raise CandidateNotFound(
                f"Unable to find candidates for {requirement.project_name}. There may "
                "exist some issues with the package index or network condition."
            )
        return cans

    def search(self, query: str) -> SearchResult:
        pypi_simple = self.sources[0]["url"].rstrip("/")
        results = []

        if pypi_simple.endswith("/simple"):
            search_url = pypi_simple[:-6] + "search"
        else:
            search_url = pypi_simple + "/search"

        with self.environment.get_finder() as finder:
            session = finder.session  # type: ignore
            resp = session.get(search_url, params={"q": query})
            if resp.status_code == 404:
                self.environment.project.core.ui.echo(
                    termui.yellow(
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


class LockedRepository(BaseRepository):
    def __init__(
        self,
        lockfile: Mapping[str, Any],
        sources: List[Source],
        environment: Environment,
    ) -> None:
        super().__init__(sources, environment)
        self.packages: Dict[tuple, Candidate] = {}
        self.file_hashes: Dict[Tuple[str, str], Dict[str, str]] = {}
        self.candidate_info: Dict[tuple, CandidateInfo] = {}
        self._read_lockfile(lockfile)

    @property
    def all_candidates(self) -> Dict[str, Candidate]:
        return {can.req.identify(): can for can in self.packages.values()}

    def _read_lockfile(self, lockfile: Mapping[str, Any]) -> None:
        for package in lockfile.get("package", []):
            version = package.get("version")
            if version:
                package["version"] = f"=={version}"
            package_name = package.pop("name")
            req_dict = {
                k: v
                for k, v in package.items()
                if k not in ("dependencies", "requires_python", "summary")
            }
            req = Requirement.from_req_dict(package_name, req_dict)
            can = Candidate(req, self.environment, name=package_name, version=version)
            can_id = self._identify_candidate(can)
            self.packages[can_id] = can
            candidate_info: CandidateInfo = (
                package.get("dependencies", []),
                package.get("requires_python", ""),
                package.get("summary", ""),
            )
            self.candidate_info[can_id] = candidate_info

        for key, hashes in lockfile.get("metadata", {}).get("files", {}).items():
            self.file_hashes[tuple(key.split(None, 1))] = {  # type: ignore
                item["file"]: item["hash"] for item in hashes
            }

    def _identify_candidate(self, candidate: Candidate) -> tuple:
        url = getattr(candidate.req, "url", None)
        return (
            candidate.identify(),
            candidate.version,
            url_without_fragments(url) if url else None,
            candidate.req.editable,
        )

    def _get_dependencies_from_lockfile(self, candidate: Candidate) -> CandidateInfo:
        return self.candidate_info[self._identify_candidate(candidate)]

    def dependency_generators(self) -> Iterable[Callable[[Candidate], CandidateInfo]]:
        return (self._get_dependencies_from_cache, self._get_dependencies_from_lockfile)

    def get_dependencies(
        self, candidate: Candidate
    ) -> Tuple[List[Requirement], PySpecSet, str]:
        reqs, python, summary = super().get_dependencies(candidate)
        reqs = [
            req
            for req in reqs
            if not req.marker
            or req.marker.evaluate(self.environment.marker_environment)
        ]
        return reqs, python, summary

    def find_candidates(
        self,
        requirement: Requirement,
        requires_python: PySpecSet = ALLOW_ALL_PYTHON,
        allow_prereleases: Optional[bool] = None,
        allow_all: bool = False,
    ) -> Iterable[Candidate]:
        for key, info in self.candidate_info.items():
            if key[0] != requirement.identify():
                continue
            if not (requires_python & PySpecSet(info[1])).contains(
                str(self.environment.interpreter.version)
            ):
                continue
            can = self.packages[key]
            can.requires_python = info[1]
            can.req = requirement
            yield can

    def get_hashes(self, candidate: Candidate) -> Optional[Dict[str, str]]:
        assert candidate.name
        return self.file_hashes.get(
            (normalize_name(candidate.name), candidate.version or "")
        )
