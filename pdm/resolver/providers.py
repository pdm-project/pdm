from __future__ import annotations

from typing import Any, Iterable, Iterator, Mapping, Sequence

from resolvelib import AbstractProvider
from resolvelib.resolvers import RequirementInformation

from pdm.models.candidates import Candidate
from pdm.models.repositories import BaseRepository
from pdm.models.requirements import Requirement
from pdm.resolver.python import (
    PythonCandidate,
    PythonRequirement,
    find_python_matches,
    is_python_satisfied_by,
)
from pdm.utils import url_without_fragments


class BaseProvider(AbstractProvider):
    def __init__(
        self, repository: BaseRepository, allow_prereleases: bool | None = None
    ) -> None:
        self.repository = repository
        self.allow_prereleases = allow_prereleases  # Root allow_prereleases value
        self.fetched_dependencies: dict[str, list[Requirement]] = {}

    def requirement_preference(self, requirement: Requirement) -> tuple:
        """Return the preference of a requirement to find candidates.

        - Editable requirements are preferered.
        - File links are preferred.
        - The one with narrower specifierset is preferred.
        """
        editable = requirement.editable
        is_file = requirement.is_file_or_url
        is_prerelease = (
            requirement.prerelease
            or requirement.specifier is not None
            and bool(requirement.specifier.prereleases)
        )
        specifier_parts = len(requirement.specifier) if requirement.specifier else 0
        return (editable, is_file, is_prerelease, specifier_parts)

    def identify(self, requirement_or_candidate: Requirement | Candidate) -> str:
        return requirement_or_candidate.identify()

    def get_preference(
        self,
        identifier: str,
        resolutions: dict[str, Candidate],
        candidates: dict[str, Iterator[Candidate]],
        information: dict[str, Iterator[RequirementInformation]],
        backtrack_causes: Sequence[RequirementInformation],
    ) -> tuple[int, ...]:
        is_backtrack_cause = int(
            bool(backtrack_causes)
            and backtrack_causes[0].requirement.identify() == identifier
        )
        required_by = sum(
            0 if info.parent is None else 1 for info in information[identifier]
        )  # top-level requirements are resolved first
        num_candidates = sum(1 for _ in candidates[identifier])
        return (-is_backtrack_cause, required_by, num_candidates)

    def find_matches(
        self,
        identifier: str,
        requirements: Mapping[str, Iterator[Requirement]],
        incompatibilities: Mapping[str, Iterator[Candidate]],
    ) -> Iterable[Candidate]:
        incompat = list(incompatibilities[identifier])
        if identifier == "python":
            candidates = find_python_matches(
                identifier, requirements, self.repository.environment
            )
            return [c for c in candidates if c not in incompat]
        reqs = sorted(
            requirements[identifier], key=self.requirement_preference, reverse=True
        )
        file_req = next((req for req in reqs if not req.is_named), None)
        if file_req:
            can = Candidate(file_req, self.repository.environment)
            can.metadata
            candidates = [can]
        else:
            req = reqs[0]
            candidates = self.repository.find_candidates(
                req, req.prerelease or self.allow_prereleases
            )
        return [
            can
            for can in candidates
            if can not in incompat and all(self.is_satisfied_by(r, can) for r in reqs)
        ]

    def is_satisfied_by(self, requirement: Requirement, candidate: Candidate) -> bool:
        if isinstance(requirement, PythonRequirement):
            return is_python_satisfied_by(requirement, candidate)
        if not requirement.is_named:
            return not candidate.req.is_named and url_without_fragments(
                candidate.req.url
            ) == url_without_fragments(requirement.url)
        version = candidate.version or candidate.metadata.version
        allow_prereleases = self.allow_prereleases
        if allow_prereleases is None:
            # if not specified, should allow what `find_candidates()` returns
            allow_prereleases = True
        return requirement.specifier.contains(version, allow_prereleases)

    def get_dependencies(self, candidate: Candidate) -> list[Requirement]:
        if isinstance(candidate, PythonCandidate):
            return []
        deps, requires_python, _ = self.repository.get_dependencies(candidate)

        # Filter out incompatible dependencies(e.g. functools32) early so that
        # we don't get errors when building wheels.
        valid_deps: list[Requirement] = []
        for dep in deps:
            if (
                dep.requires_python
                & requires_python
                & candidate.req.requires_python
                & self.repository.environment.python_requires
            ).is_impossible:
                continue
            dep.requires_python &= candidate.req.requires_python
            valid_deps.append(dep)
        candidate_key = self.identify(candidate)
        self.fetched_dependencies[candidate_key] = valid_deps[:]
        # A candidate contributes to the Python requirements only when:
        # It isn't an optional dependency, or the requires-python doesn't cover
        # the req's requires-python.
        # For example, A v1 requires python>=3.6, it not eligible on a project with
        # requires-python=">=2.7". But it is eligible if A has environment marker
        # A1; python_version>='3.8'
        new_requires_python = (
            candidate.req.requires_python & self.repository.environment.python_requires
        )
        if not requires_python.is_superset(new_requires_python):
            valid_deps.append(PythonRequirement.from_pyspec_set(requires_python))
        return valid_deps


class ReusePinProvider(BaseProvider):
    """A provider that reuses preferred pins if possible.

    This is used to implement "add", "remove", and "reuse upgrade",
    where already-pinned candidates in lockfile should be preferred.
    """

    def __init__(
        self,
        preferred_pins: dict[str, Candidate],
        tracked_names: Iterable[str],
        *args: Any
    ) -> None:
        super().__init__(*args)
        self.preferred_pins = preferred_pins
        self.tracked_names = set(tracked_names)

    def find_matches(
        self,
        identifier: str,
        requirements: Mapping[str, Iterator[Requirement]],
        incompatibilities: Mapping[str, Iterator[Candidate]],
    ) -> Iterable[Candidate]:
        if identifier not in self.tracked_names and identifier in self.preferred_pins:
            pin = self.preferred_pins[identifier]
            incompat = list(incompatibilities[identifier])
            pin._preferred = True
            if pin not in incompat and all(
                self.is_satisfied_by(r, pin) for r in requirements[identifier]
            ):
                yield pin
        yield from super().find_matches(identifier, requirements, incompatibilities)


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

    def get_dependencies(self, candidate: Candidate) -> list[Requirement]:
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
        identifier: str,
        resolutions: dict[str, Candidate],
        candidates: dict[str, Iterator[Candidate]],
        information: dict[str, Iterator[RequirementInformation]],
        backtrack_causes: Sequence[RequirementInformation],
    ) -> tuple[int, ...]:
        # Resolve tracking packages so we have a chance to unpin them first.
        return (-int(identifier in self.tracked_names),) + super().get_preference(
            identifier, resolutions, candidates, information, backtrack_causes
        )
