from __future__ import annotations

import dataclasses
import fnmatch
import re
import sys
import warnings
from functools import wraps
from typing import TYPE_CHECKING, Generator, NamedTuple, TypeVar, cast

from pdm import termui
from pdm._types import NotSet, NotSetType
from pdm.exceptions import CandidateInfoNotFound, PackageWarning
from pdm.models.candidates import Candidate
from pdm.models.markers import EnvSpec
from pdm.models.requirements import Requirement, parse_line
from pdm.models.specifiers import PySpecSet
from pdm.utils import deprecation_warning, filtered_sources, normalize_name

if TYPE_CHECKING:
    from typing import Callable, Iterable

    from unearth import Link

    from pdm._types import FileHash, RepositoryConfig, SearchResults
    from pdm.environments import BaseEnvironment


T = TypeVar("T", bound="BaseRepository")


class CandidateMetadata(NamedTuple):
    dependencies: list[Requirement]
    requires_python: str
    summary: str


def cache_result(func: Callable[[T, Candidate], CandidateMetadata]) -> Callable[[T, Candidate], CandidateMetadata]:
    @wraps(func)
    def wrapper(self: T, candidate: Candidate) -> CandidateMetadata:
        result = func(self, candidate)
        prepared = candidate.prepared
        info = ([r.as_line() for r in result.dependencies], result.requires_python, result.summary)
        if prepared and prepared.should_cache():
            self._candidate_info_cache.set(candidate, info)
        return result

    return wrapper


class BaseRepository:
    """A Repository acts as the source of packages and metadata."""

    def __init__(
        self,
        sources: list[RepositoryConfig],
        environment: BaseEnvironment,
        ignore_compatibility: bool | NotSetType = NotSet,
        env_spec: EnvSpec | None = None,
    ) -> None:
        """
        :param sources: a list of sources to download packages from.
        :param environment: the bound environment instance.
        :param ignore_compatibility: (DEPRECATED)if True, don't evaluate candidate against
            the current environment.
        :param env_spec: the environment specifier to filter the candidates.
        """
        from pdm.resolver.reporters import LockReporter

        self.sources = sources
        self.environment = environment
        self._candidate_info_cache = environment.project.make_candidate_info_cache()
        self._hash_cache = environment.project.make_hash_cache()
        self.has_warnings = False
        self.collected_groups: set[str] = set()
        self.find_dependencies_from_local = True
        if ignore_compatibility is not NotSet:  # pragma: no cover
            deprecation_warning(
                "The ignore_compatibility argument is deprecated and will be removed in the future. "
                "Pass in env_set instead. This repository doesn't support lock targets.",
                stacklevel=2,
            )
        else:
            ignore_compatibility = True
        if env_spec is None:  # pragma: no cover
            if ignore_compatibility:
                env_spec = environment.allow_all_spec
            else:
                env_spec = environment.spec
        self.env_spec = env_spec
        self.reporter = LockReporter()

    def get_filtered_sources(self, req: Requirement) -> list[RepositoryConfig]:
        """Get matching sources based on the index attribute."""
        return filtered_sources(self.sources, req.key)

    def get_dependencies(self, candidate: Candidate) -> tuple[list[Requirement], PySpecSet, str]:
        """Get (dependencies, python_specifier, summary) of the candidate."""
        requires_python, summary = "", ""
        requirements: list[Requirement] = []
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
        if candidate.req.extras:
            # XXX: If the requirement has extras, add the original candidate
            # (without extras) as its dependency. This ensures the same package with
            # different extras resolve to the same version.
            self_req = dataclasses.replace(
                candidate.req.as_pinned_version(candidate.version),
                extras=None,
                marker=None,
            )
            requirements.insert(0, self_req)
        # Store the metadata on the candidate for caching
        candidate.requires_python = requires_python
        candidate.summary = summary
        return requirements, PySpecSet(requires_python), summary

    def _find_candidates(self, requirement: Requirement, minimal_version: bool) -> Iterable[Candidate]:
        raise NotImplementedError

    def is_this_package(self, requirement: Requirement) -> bool:
        """Whether the requirement is the same as this package"""
        project = self.environment.project
        return requirement.is_named and project.is_distribution and requirement.key == normalize_name(project.name)

    def make_this_candidate(self, requirement: Requirement) -> Candidate:
        """Make a candidate for this package.
        In this case the finder will look for a candidate from the package sources
        """
        from unearth import Link

        project = self.environment.project
        link = Link.from_path(project.root)
        candidate = Candidate(requirement, project.name, link=link)
        with self.reporter.make_candidate_reporter(candidate) as reporter:
            candidate.prepare(self.environment, reporter=reporter).metadata
        return candidate

    def _should_ignore_package_warning(self, requirement: Requirement) -> bool:
        ignore_settings: list[str] = self.environment.project.pyproject.settings.get("ignore_package_warnings", [])
        package_name = requirement.key
        assert package_name is not None
        for pat in ignore_settings:
            pat = re.sub(r"[^A-Za-z0-9?*\[\]]+", "-", pat).lower()
            if fnmatch.fnmatch(package_name, pat):
                return True
        return False

    def find_candidates(
        self,
        requirement: Requirement,
        allow_prereleases: bool | None = None,
        ignore_requires_python: bool = False,
        minimal_version: bool = False,
    ) -> Iterable[Candidate]:
        """Find candidates of the given NamedRequirement. Let it to be implemented in
        subclasses.

        :param requirement: the requirement to find
        :param allow_prereleases: whether to include pre-releases
        :param ignore_requires_python: whether to ignore the requires-python marker
        :param minimal_version: whether to prefer the minimal versions of the package
        """
        # `allow_prereleases` is None means to let the specifier decide whether to
        # include prereleases
        from unearth.utils import LazySequence

        if self.is_this_package(requirement):
            return [self.make_this_candidate(requirement)]
        requires_python = requirement.requires_python & self.env_spec.requires_python
        cans = LazySequence(self._find_candidates(requirement, minimal_version=minimal_version))
        applicable_cans = LazySequence(
            c
            for c in cans
            if requirement.specifier.contains(c.version, allow_prereleases)  # type: ignore[arg-type, union-attr]
        )

        def filter_candidates_with_requires_python(candidates: Iterable[Candidate]) -> Generator[Candidate]:
            env_requires_python = PySpecSet(self.env_spec.requires_python)
            if ignore_requires_python:
                yield from candidates
                return

            def python_specifier(spec: str | PySpecSet) -> str:
                if isinstance(spec, PySpecSet):
                    spec = str(spec)
                return "all Python versions" if not spec else f"Python{spec}"

            for candidate in candidates:
                if not requires_python.is_subset(candidate.requires_python):
                    if self._should_ignore_package_warning(requirement):
                        continue
                    working_requires_python = env_requires_python & PySpecSet(candidate.requires_python)
                    if working_requires_python.is_empty():  # pragma: no cover
                        continue
                    warnings.warn(
                        f"Skipping {candidate.name}@{candidate.version} because it requires "
                        f"{python_specifier(candidate.requires_python)} but the lock targets to work with "
                        f"{python_specifier(env_requires_python)}. Instead, another version of "
                        f"{candidate.name} that supports {python_specifier(env_requires_python)} will "
                        f"be used.\nIf you want to install {candidate.name}@{candidate.version}, "
                        "narrow down the `requires-python` range to "
                        f'include this version. For example, "{working_requires_python}" should work.',
                        PackageWarning,
                        stacklevel=4,
                    )
                    self.has_warnings = True
                else:
                    yield candidate

        applicable_cans_python_compatible = LazySequence(filter_candidates_with_requires_python(applicable_cans))
        # Evaluate data-requires-python attr and discard incompatible candidates
        # to reduce the number of candidates to resolve.
        if applicable_cans_python_compatible:
            applicable_cans = applicable_cans_python_compatible

        if not applicable_cans:
            termui.logger.debug("\tCould not find any matching candidates.")

        if not applicable_cans and allow_prereleases is None:
            # No non-pre-releases is found, force pre-releases now
            applicable_cans = LazySequence(
                c
                for c in cans
                if requirement.specifier.contains(c.version, True)  # type: ignore[arg-type, union-attr]
            )
            applicable_cans_python_compatible = LazySequence(filter_candidates_with_requires_python(applicable_cans))
            if applicable_cans_python_compatible:
                applicable_cans = applicable_cans_python_compatible

            if not applicable_cans:
                termui.logger.debug(
                    "\tCould not find any matching candidates even when considering pre-releases.",
                )

        def log_candidates(title: str, candidates: Iterable[Candidate], max_lines: int = 10) -> None:
            termui.logger.debug("\t" + title)
            logged_lines = set()
            for can in candidates:
                new_line = f"\t  {can!r}"
                if new_line not in logged_lines:
                    logged_lines.add(new_line)
                    if len(logged_lines) > max_lines:
                        termui.logger.debug("\t  ... [more]")
                        break
                    else:
                        termui.logger.debug(new_line)

        if self.environment.project.core.ui.verbosity >= termui.Verbosity.DEBUG:
            if applicable_cans:
                log_candidates("Found matching candidates:", applicable_cans)
            elif cans:
                log_candidates("Found but non-matching candidates:", cans)

        return applicable_cans

    def _get_dependencies_from_cache(self, candidate: Candidate) -> CandidateMetadata:
        try:
            info = self._candidate_info_cache.get(candidate)
        except KeyError:
            raise CandidateInfoNotFound(candidate) from None

        deps: list[Requirement] = []
        for line in info[0]:
            deps.append(parse_line(line))
        termui.logger.debug("Using cached metadata for %s", candidate)
        return CandidateMetadata(deps, info[1], info[2])

    @cache_result
    def _get_dependencies_from_metadata(self, candidate: Candidate) -> CandidateMetadata:
        with self.reporter.make_candidate_reporter(candidate) as reporter:
            prepared = candidate.prepare(self.environment, reporter=reporter)
            deps = prepared.get_dependencies_from_metadata()
            requires_python = candidate.requires_python
            summary = prepared.metadata.metadata.get("Summary", "")
        return CandidateMetadata(deps, requires_python, summary)

    def _get_dependencies_from_local_package(self, candidate: Candidate) -> CandidateMetadata:
        """Adds the local package as a candidate only if the candidate
        name is the same as the local package."""
        project = self.environment.project
        if not project.is_distribution or candidate.name != project.name:
            raise CandidateInfoNotFound(candidate) from None

        reqs: list[Requirement] = []
        if candidate.req.extras is not None:
            all_groups = set(project.iter_groups())
            for extra in candidate.req.extras:
                if extra in all_groups:
                    reqs.extend(project.get_dependencies(extra))
                    self.collected_groups.add(extra)
        return CandidateMetadata(
            reqs,
            str(self.environment.python_requires),
            project.pyproject.metadata.get("description", "UNKNOWN"),
        )

    def get_hashes(self, candidate: Candidate) -> list[FileHash]:
        """Get hashes of all possible installable candidates
        of a given package version.
        """
        if (
            candidate.req.is_vcs or candidate.req.is_file_or_url and candidate.req.is_local_dir  # type: ignore[attr-defined]
        ):
            return []
        if candidate.hashes:
            return candidate.hashes
        req = candidate.req.as_pinned_version(candidate.version)
        comes_from = candidate.link.comes_from if candidate.link else None
        result: list[FileHash] = []
        logged = False
        respect_source_order = self.environment.project.pyproject.settings.get("resolution", {}).get(
            "respect-source-order", False
        )
        sources = self.get_filtered_sources(candidate.req)
        if req.is_named and respect_source_order and comes_from:
            sources = [s for s in sources if comes_from.startswith(cast(str, s.url))]

        if req.is_file_or_url:
            this_link = cast("Link", candidate.prepare(self.environment).link)
            links: list[Link] = [this_link]
        else:  # the req must be a named requirement
            with self.environment.get_finder(sources, env_spec=self.env_spec) as finder:
                links = [package.link for package in finder.find_matches(req.as_line())]
        for link in links:
            if not link or link.is_vcs or link.is_file and link.file_path.is_dir():
                # The links found can still be a local directory or vcs, skippping it.
                continue
            if not logged:
                termui.logger.info("Fetching hashes for %s", candidate)
                logged = True
            result.append(
                {
                    "url": link.url_without_fragment,
                    "file": link.filename,
                    "hash": self._hash_cache.get_hash(link, self.environment.session),
                }
            )
        return result

    def dependency_generators(self) -> Iterable[Callable[[Candidate], CandidateMetadata]]:
        """Return an iterable of getter functions to get dependencies, which will be
        called one by one.
        """
        raise NotImplementedError

    def search(self, query: str) -> SearchResults:
        """Search package by name or summary.

        :param query: query string
        :returns: search result, a dictionary of name: package metadata
        """
        raise NotImplementedError

    def fetch_hashes(self, candidates: Iterable[Candidate]) -> None:
        """Fetch hashes for candidates in parallel"""
        from concurrent.futures import ThreadPoolExecutor

        def do_fetch(candidate: Candidate) -> None:
            candidate.hashes = self.get_hashes(candidate)

        with ThreadPoolExecutor() as executor:
            executor.map(do_fetch, candidates)
