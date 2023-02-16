from __future__ import annotations

import os
from typing import TYPE_CHECKING, Callable, cast

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from resolvelib import AbstractProvider

from pdm.models.candidates import Candidate, make_candidate
from pdm.models.repositories import LockedRepository
from pdm.models.requirements import FileRequirement, parse_requirement, strip_extras
from pdm.resolver.python import (
    PythonCandidate,
    PythonRequirement,
    find_python_matches,
    is_python_satisfied_by,
)
from pdm.utils import is_url, url_without_fragments

if TYPE_CHECKING:
    from typing import Any, Iterable, Iterator, Mapping, Sequence

    from resolvelib.resolvers import RequirementInformation

    from pdm._types import Comparable
    from pdm.models.repositories import BaseRepository
    from pdm.models.requirements import Requirement


class BaseProvider(AbstractProvider):
    def __init__(
        self,
        repository: BaseRepository,
        allow_prereleases: bool | None = None,
        overrides: dict[str, str] | None = None,
    ) -> None:
        self.repository = repository
        self.allow_prereleases = allow_prereleases  # Root allow_prereleases value
        self.fetched_dependencies: dict[tuple[str, str | None], list[Requirement]] = {}
        self.overrides = overrides or {}
        self._known_depth: dict[str, int] = {}

    def requirement_preference(self, requirement: Requirement) -> Comparable:
        """Return the preference of a requirement to find candidates.

        - Editable requirements are preferered.
        - File links are preferred.
        - The one with narrower specifierset is preferred.
        """
        editable = requirement.editable
        is_named = requirement.is_named
        is_prerelease = (
            requirement.prerelease or requirement.specifier is not None and bool(requirement.specifier.prereleases)
        )
        specifier_parts = len(requirement.specifier) if requirement.specifier else 0
        return (not editable, is_named, not is_prerelease, -specifier_parts)

    def identify(self, requirement_or_candidate: Requirement | Candidate) -> str:
        return requirement_or_candidate.identify()

    def get_preference(
        self,
        identifier: str,
        resolutions: dict[str, Candidate],
        candidates: dict[str, Iterator[Candidate]],
        information: dict[str, Iterator[RequirementInformation]],
        backtrack_causes: Sequence[RequirementInformation],
    ) -> tuple[Comparable, ...]:
        is_top = any(parent is None for _, parent in information[identifier])
        is_backtrack_cause = any(
            requirement.identify() == identifier or parent and parent.identify() == identifier
            for requirement, parent in backtrack_causes
        )
        if is_top:
            dep_depth = 1
        else:
            parent_depths = (
                self._known_depth[parent.identify()] if parent is not None else 0
                for _, parent in information[identifier]
            )
            dep_depth = min(parent_depths, default=0) + 1
        # Use the REAL identifier as it may be updated after candidate preparation.
        self._known_depth[self.identify(next(candidates[identifier]))] = dep_depth
        is_file_or_url = any(not requirement.is_named for requirement, _ in information[identifier])
        operators = [
            spec.operator for req, _ in information[identifier] if req.specifier is not None for spec in req.specifier
        ]
        is_python = identifier == "python"
        is_pinned = any(op[:2] == "==" for op in operators)
        constraints = len(operators)
        return (
            not is_python,
            not is_top,
            not is_file_or_url,
            not is_pinned,
            not is_backtrack_cause,
            dep_depth,
            -constraints,
            identifier,
        )

    def get_override_candidates(self, identifier: str) -> Iterable[Candidate]:
        requested = self.overrides[identifier]
        if is_url(requested):
            req = f"{identifier} @ {requested}"
        else:
            try:
                SpecifierSet(requested)
            except InvalidSpecifier:  # handle bare versions
                req = f"{identifier}=={requested}"
            else:
                req = f"{identifier}{requested}"
        return self._find_candidates(parse_requirement(req))

    def _find_candidates(self, requirement: Requirement) -> Iterable[Candidate]:
        if not requirement.is_named and not isinstance(self.repository, LockedRepository):
            can = make_candidate(requirement)
            if not can.name:
                can.prepare(self.repository.environment).metadata
            return [can]
        else:
            return self.repository.find_candidates(requirement, requirement.prerelease or self.allow_prereleases)

    def find_matches(
        self,
        identifier: str,
        requirements: Mapping[str, Iterator[Requirement]],
        incompatibilities: Mapping[str, Iterator[Candidate]],
    ) -> Callable[[], Iterator[Candidate]]:
        def matches_gen() -> Iterator[Candidate]:
            incompat = list(incompatibilities[identifier])
            if identifier == "python":
                candidates = find_python_matches(identifier, requirements)
                return (c for c in candidates if c not in incompat)
            elif identifier in self.overrides:
                return iter(self.get_override_candidates(identifier))
            reqs = sorted(requirements[identifier], key=self.requirement_preference)
            candidates = self._find_candidates(reqs[0])
            return (
                can for can in candidates if can not in incompat and all(self.is_satisfied_by(r, can) for r in reqs)
            )

        return matches_gen

    def _compare_file_reqs(self, req1: FileRequirement, req2: FileRequirement) -> bool:
        backend = self.repository.environment.project.backend
        if req1.path and req2.path:
            return os.path.normpath(req1.path) == os.path.normpath(req2.path)
        left = backend.expand_line(url_without_fragments(req1.get_full_url()))
        right = backend.expand_line(url_without_fragments(req2.get_full_url()))
        return left == right

    def is_satisfied_by(self, requirement: Requirement, candidate: Candidate) -> bool:
        if isinstance(requirement, PythonRequirement):
            return is_python_satisfied_by(requirement, candidate)
        elif candidate.identify() in self.overrides:
            return True
        if not requirement.is_named:
            if candidate.req.is_named:
                return False
            return self._compare_file_reqs(requirement, candidate.req)  # type: ignore[arg-type]
        version = candidate.version
        this_name = self.repository.environment.project.name
        if version is None or candidate.name == this_name:
            # This should be a URL candidate or self package, consider it to be matching
            return True
        # Allow prereleases if: 1) it is not specified in the tool settings or
        # 2) the candidate doesn't come from PyPI index.
        allow_prereleases = self.allow_prereleases in (True, None) or not candidate.req.is_named
        return cast(SpecifierSet, requirement.specifier).contains(version, allow_prereleases)

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
        self.fetched_dependencies[candidate.dep_key] = valid_deps[:]
        # A candidate contributes to the Python requirements only when:
        # It isn't an optional dependency, or the requires-python doesn't cover
        # the req's requires-python.
        # For example, A v1 requires python>=3.6, it not eligible on a project with
        # requires-python=">=2.7". But it is eligible if A has environment marker
        # A1; python_version>='3.8'
        new_requires_python = candidate.req.requires_python & self.repository.environment.python_requires
        if candidate.identify() not in self.overrides and not requires_python.is_superset(new_requires_python):
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
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.preferred_pins = preferred_pins
        self.tracked_names = set(tracked_names)

    def find_matches(
        self,
        identifier: str,
        requirements: Mapping[str, Iterator[Requirement]],
        incompatibilities: Mapping[str, Iterator[Candidate]],
    ) -> Callable[[], Iterator[Candidate]]:
        super_find = super().find_matches(identifier, requirements, incompatibilities)
        bare_name = strip_extras(identifier)[0]

        def matches_gen() -> Iterator[Candidate]:
            if bare_name not in self.tracked_names and identifier in self.preferred_pins:
                pin = self.preferred_pins[identifier]
                incompat = list(incompatibilities[identifier])
                demanded_req = next(requirements[identifier], None)
                if demanded_req and demanded_req.is_named:
                    pin.req = demanded_req
                pin._preferred = True  # type: ignore[attr-defined]
                if pin not in incompat and all(self.is_satisfied_by(r, pin) for r in requirements[identifier]):
                    yield pin
            yield from super_find()

        return matches_gen


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
        if requirement.key in self.tracked_names and getattr(candidate, "_preferred", False):
            return False
        return super().is_satisfied_by(requirement, candidate)

    def get_dependencies(self, candidate: Candidate) -> list[Requirement]:
        # If this package is being tracked for upgrade, remove pins of its
        # dependencies, and start tracking these new packages.
        dependencies = super().get_dependencies(candidate)
        if self.identify(candidate) in self.tracked_names:
            for dependency in dependencies:
                if dependency.key:
                    self.tracked_names.add(dependency.key)
        return dependencies

    def get_preference(
        self,
        identifier: str,
        resolutions: dict[str, Candidate],
        candidates: dict[str, Iterator[Candidate]],
        information: dict[str, Iterator[RequirementInformation]],
        backtrack_causes: Sequence[RequirementInformation],
    ) -> tuple[Comparable, ...]:
        # Resolve tracking packages so we have a chance to unpin them first.
        (python, *others) = super().get_preference(identifier, resolutions, candidates, information, backtrack_causes)
        return (python, identifier not in self.tracked_names, *others)
