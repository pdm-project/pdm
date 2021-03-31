from typing import Any, Dict, Iterable, List, Optional, Union

from resolvelib import AbstractProvider
from resolvelib.resolvers import RequirementInformation

from pdm.models.candidates import Candidate
from pdm.models.repositories import BaseRepository
from pdm.models.requirements import Requirement
from pdm.models.specifiers import PySpecSet
from pdm.utils import url_without_fragments


class BaseProvider(AbstractProvider):
    def __init__(
        self,
        repository: BaseRepository,
        requires_python: PySpecSet,
        allow_prereleases: Optional[bool] = None,
    ) -> None:
        self.repository = repository
        self.requires_python = requires_python  # Root python_requires value
        self.allow_prereleases = allow_prereleases  # Root allow_prereleases value
        self.requires_python_collection: Dict[Optional[str], PySpecSet] = {}
        self.summary_collection: Dict[str, str] = {}
        self.fetched_dependencies: Dict[str, List[Requirement]] = {}

    def identify(self, req: Union[Requirement, Candidate]) -> Optional[str]:
        return req.identify()

    def get_preference(
        self,
        resolution: Candidate,
        candidates: List[Candidate],
        information: List[RequirementInformation],
    ) -> int:
        return len(candidates)

    def find_matches(self, requirements: List[Requirement]) -> Iterable[Candidate]:
        file_req = next((req for req in requirements if not req.is_named), None)
        if file_req:
            can = Candidate(file_req, self.repository.environment)
            can.get_metadata()
            candidates = [can]
        else:
            candidates = self.repository.find_candidates(
                requirements[0], self.requires_python, self.allow_prereleases
            )
        return [
            can
            for can in candidates
            if all(self.is_satisfied_by(r, can) for r in requirements)
        ]

    def is_satisfied_by(self, requirement: Requirement, candidate: Candidate) -> bool:
        if not requirement.is_named:
            return not candidate.req.is_named and url_without_fragments(
                candidate.req.url
            ) == url_without_fragments(requirement.url)
        if not candidate.version:
            candidate.get_metadata()
        if getattr(candidate, "_preferred", False) and not candidate._requires_python:
            candidate.requires_python = str(
                self.repository.get_dependencies(candidate)[1]
            )
        allow_prereleases = requirement.allow_prereleases
        if allow_prereleases is None:
            allow_prereleases = self.allow_prereleases
        if allow_prereleases is None:
            # if not specified, should allow what `find_candidates()` returns
            allow_prereleases = True
        requires_python = self.requires_python & requirement.requires_python
        return requirement.specifier.contains(
            candidate.version, allow_prereleases
        ) and requires_python.is_subset(candidate.requires_python)

    def get_dependencies(self, candidate: Candidate) -> List[Requirement]:
        deps, requires_python, summary = self.repository.get_dependencies(candidate)

        # Filter out incompatible dependencies(e.g. functools32) early so that
        # we don't get errors when building wheels.
        valid_deps: List[Requirement] = []
        for dep in deps:
            if (
                dep.requires_python & requires_python & self.requires_python
            ).is_impossible:
                continue
            dep.requires_python &= candidate.req.requires_python
            valid_deps.append(dep)

        candidate_key = self.identify(candidate)
        self.fetched_dependencies[candidate_key] = valid_deps
        self.summary_collection[candidate.req.key] = summary
        self.requires_python_collection[candidate.req.key] = requires_python
        return valid_deps

    def get_hashes(self, candidate: Candidate) -> Optional[Dict[str, str]]:
        return self.repository.get_hashes(candidate)


class ReusePinProvider(BaseProvider):
    """A provider that reuses preferred pins if possible.

    This is used to implement "add", "remove", and "reuse upgrade",
    where already-pinned candidates in lockfile should be preferred.
    """

    def __init__(
        self,
        preferred_pins: Dict[str, Candidate],
        tracked_names: Iterable[str],
        *args: Any
    ) -> None:
        super().__init__(*args)
        self.preferred_pins = preferred_pins
        self.tracked_names = set(tracked_names)

    def find_matches(self, requirements: List[Requirement]) -> Iterable[Candidate]:
        ident = self.identify(requirements[0])
        if ident not in self.tracked_names and ident in self.preferred_pins:
            pin = self.preferred_pins[ident]
            pin._preferred = True
            yield pin
        yield from super().find_matches(requirements)


class EagerUpdateProvider(ReusePinProvider):
    """A specialized provider to handle an "eager" upgrade strategy.

    An eager upgrade tries to upgrade not only packages specified, but also
    their dependencies (recursively). This contrasts to the "only-if-needed"
    default, which only promises to upgrade the specified package, and
    prevents touching anything else if at all possible.

    The provider is implemented as to keep track of all dependencies of the
    specified packages to upgrade, and free their pins when it has a chance.
    """

    def is_satisfied_by(self, requirement: Requirement, candidate: Candidate) -> bool:
        # If this is a tracking package, tell the resolver out of using the
        # preferred pin, and into a "normal" candidate selection process.
        if self.identify(requirement) in self.tracked_names and getattr(
            candidate, "_preferred", False
        ):
            return False
        return super().is_satisfied_by(requirement, candidate)

    def get_dependencies(self, candidate: Candidate) -> List[Requirement]:
        # If this package is being tracked for upgrade, remove pins of its
        # dependencies, and start tracking these new packages.
        dependencies = super().get_dependencies(candidate)
        if self.identify(candidate) in self.tracked_names:
            for dependency in dependencies:
                name = self.identify(dependency)
                self.tracked_names.add(name)
        return dependencies

    def get_preference(
        self,
        resolution: Candidate,
        candidates: List[Candidate],
        information: List[RequirementInformation],
    ) -> int:
        # Resolve tracking packages so we have a chance to unpin them first.
        name = self.identify(candidates[0])
        if name in self.tracked_names:
            return -1
        return len(candidates)
