from __future__ import annotations

import os
from typing import TYPE_CHECKING, Callable

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion
from resolvelib import AbstractProvider, RequirementsConflicted
from resolvelib.resolvers import Criterion

from pdm.exceptions import InvalidPyVersion, RequirementError
from pdm.models.candidates import Candidate
from pdm.models.repositories import LockedRepository
from pdm.models.requirements import FileRequirement, parse_requirement, strip_extras
from pdm.resolver.python import PythonCandidate, PythonRequirement, find_python_matches, is_python_satisfied_by
from pdm.termui import logger
from pdm.utils import deprecation_warning, is_url, normalize_name, parse_version, url_without_fragments

if TYPE_CHECKING:
    from typing import Any, Iterable, Iterator, Mapping, Sequence, TypeVar

    from resolvelib.resolvers import RequirementInformation

    from pdm._types import Comparable
    from pdm.models.repositories import BaseRepository
    from pdm.models.requirements import Requirement

    ProviderT = TypeVar("ProviderT", bound="type[BaseProvider]")


_PROVIDER_REGISTORY: dict[str, type[BaseProvider]] = {}


def get_provider(strategy: str) -> type[BaseProvider]:
    return _PROVIDER_REGISTORY[strategy]


def register_provider(strategy: str) -> Callable[[ProviderT], ProviderT]:
    def wrapper(cls: ProviderT) -> ProviderT:
        _PROVIDER_REGISTORY[strategy] = cls
        return cls

    return wrapper


@register_provider("all")
class BaseProvider(AbstractProvider):
    def __init__(
        self,
        repository: BaseRepository,
        allow_prereleases: bool | None = None,
        overrides: dict[str, str] | None = None,
        direct_minimal_versions: bool = False,
        *,
        locked_candidates: dict[str, Candidate],
    ) -> None:
        if overrides is not None:  # pragma: no cover
            deprecation_warning(
                "The `overrides` argument is deprecated and will be removed in the future.", stacklevel=2
            )
        if allow_prereleases is not None:  # pragma: no cover
            deprecation_warning(
                "The `allow_prereleases` argument is deprecated and will be removed in the future.", stacklevel=2
            )
        project = repository.environment.project
        self.repository = repository
        self.allow_prereleases = project.pyproject.allow_prereleases  # Root allow_prereleases value
        self.fetched_dependencies: dict[tuple[str, str | None], list[Requirement]] = {}
        self.overrides: Mapping[str, str] = {
            normalize_name(k): v for k, v in project.pyproject.resolution.get("overrides", {}).items()
        }
        self.excludes = {normalize_name(k) for k in project.pyproject.resolution.get("excludes", [])}
        self.direct_minimal_versions = direct_minimal_versions
        self.locked_candidates = locked_candidates
        self._known_depth: dict[str, int] = {}

    def requirement_preference(self, requirement: Requirement) -> Comparable:
        """Return the preference of a requirement to find candidates.

        - Editable requirements are preferered.
        - File links are preferred.
        - The one with narrower specifierset is preferred.
        """
        editable = requirement.editable
        is_named = requirement.is_named
        is_pinned = requirement.is_pinned
        is_prerelease = bool(requirement.prerelease) and bool(requirement.specifier.prereleases)
        specifier_parts = len(requirement.specifier)
        return (not editable, is_named, not is_pinned, not is_prerelease, -specifier_parts)

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
        backtrack_identifiers = {req.identify() for req, _ in backtrack_causes} | {
            parent.identify() for _, parent in backtrack_causes if parent is not None
        }
        if is_top:
            dep_depth = 1
        else:
            parent_depths = (
                self._known_depth[parent.identify()] if parent is not None else 0
                for _, parent in information[identifier]
            )
            dep_depth = min(parent_depths, default=0) + 1
        # Use the REAL identifier as it may be updated after candidate preparation.
        deps: list[Requirement] = []
        for candidate in candidates[identifier]:
            try:
                deps = self.get_dependencies(candidate)
            except RequirementsConflicted:
                continue
            break
        self._known_depth[self.identify(candidate)] = dep_depth
        is_backtrack_cause = any(dep.identify() in backtrack_identifiers for dep in deps)
        is_file_or_url = any(not requirement.is_named for requirement, _ in information[identifier])
        operators = [spec.operator for req, _ in information[identifier] for spec in req.specifier]
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

    def _is_direct_requirement(self, requirement: Requirement) -> bool:
        from collections import ChainMap

        project = self.repository.environment.project
        all_dependencies = ChainMap(*project.all_dependencies.values())
        return requirement.identify() in all_dependencies

    def _find_candidates(self, requirement: Requirement) -> Iterable[Candidate]:
        if not requirement.is_named and not isinstance(self.repository, LockedRepository):
            can = Candidate(requirement)
            if not can.name:
                can.prepare(self.repository.environment).metadata
            return [can]
        else:
            prerelease = requirement.prerelease
            if prerelease is None and (key := requirement.identify()) in self.locked_candidates:
                # keep the prerelease if it is locked
                candidate = self.locked_candidates[key]
                if candidate.version is not None:
                    try:
                        parsed_version = parse_version(candidate.version)
                    except InvalidVersion:  # pragma: no cover
                        pass
                    else:
                        if parsed_version.is_prerelease:
                            prerelease = True
            return self.repository.find_candidates(
                requirement,
                self.allow_prereleases if prerelease is None else prerelease,
                minimal_version=self.direct_minimal_versions and self._is_direct_requirement(requirement),
            )

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
            elif (name := strip_extras(identifier)[0]) in self.overrides:
                return iter(self.get_override_candidates(name))
            reqs = sorted(requirements[identifier], key=self.requirement_preference)
            if not reqs:
                return iter(())
            original_req = reqs[0]
            bare_name, extras = strip_extras(identifier)
            if extras and bare_name in requirements:
                # We should consider the requirements for both foo and foo[extra]
                reqs.extend(requirements[bare_name])
                reqs.sort(key=self.requirement_preference)
            candidates = self._find_candidates(reqs[0])
            return (
                # In some cases we will use candidates from the bare requirement,
                # this will miss the extra dependencies if any. So we associate the original
                # requirement back with the candidate since it is used by `get_dependencies()`.
                can.copy_with(original_req) if extras else can
                for can in candidates
                if can not in incompat and all(self.is_satisfied_by(r, can) for r in reqs)
            )

        return matches_gen

    def _compare_file_reqs(self, req1: FileRequirement, req2: FileRequirement) -> bool:
        backend = self.repository.environment.project.backend
        if req1.path and req2.path:
            return os.path.normpath(req1.path.absolute()) == os.path.normpath(req2.path.absolute())
        left = backend.expand_line(url_without_fragments(req1.get_full_url()))
        right = backend.expand_line(url_without_fragments(req2.get_full_url()))
        return left == right

    def is_satisfied_by(self, requirement: Requirement, candidate: Candidate) -> bool:
        if isinstance(requirement, PythonRequirement):
            return is_python_satisfied_by(requirement, candidate)
        elif (name := candidate.identify()) in self.overrides or strip_extras(name)[0] in self.overrides:
            return True
        if not requirement.is_named:
            if candidate.req.is_named:
                return False
            can_req = candidate.req
            if requirement.is_vcs and can_req.is_vcs:
                return can_req.vcs == requirement.vcs and can_req.repo == requirement.repo  # type: ignore[attr-defined]
            return self._compare_file_reqs(requirement, can_req)  # type: ignore[arg-type]
        version = candidate.version
        this_name = self.repository.environment.project.name
        if version is None or candidate.name == this_name:
            # This should be a URL candidate or self package, consider it to be matching
            return True
        # Allow prereleases if: 1) it is not specified in the tool settings or
        # 2) the candidate doesn't come from PyPI index.
        allow_prereleases = self.allow_prereleases in (True, None) or not candidate.req.is_named
        return requirement.specifier.contains(version, allow_prereleases)

    def get_dependencies(self, candidate: Candidate) -> list[Requirement]:
        if isinstance(candidate, PythonCandidate):
            return []
        try:
            deps, requires_python, _ = self.repository.get_dependencies(candidate)
        except (RequirementError, InvalidPyVersion, InvalidSpecifier) as e:
            # When the metadata is invalid, skip this candidate by marking it as conflicting.
            # Here we pass an empty criterion so it doesn't provide any info to the resolution.
            logger.error("Invalid metadata in %s: %s", candidate, e)
            raise RequirementsConflicted(Criterion([], [], [])) from None

        # Filter out incompatible dependencies(e.g. functools32) early so that
        # we don't get errors when building wheels.
        valid_deps: list[Requirement] = []
        for dep in deps:
            if (
                dep.requires_python
                & requires_python
                & candidate.req.requires_python
                & self.repository.environment.python_requires
            ).is_empty():
                continue
            if dep.identify() in self.excludes:
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
        if not (
            candidate.identify() in self.overrides
            or new_requires_python.is_empty()
            or requires_python.is_superset(new_requires_python)
        ):
            valid_deps.append(PythonRequirement.from_pyspec_set(requires_python))
        return valid_deps


@register_provider("reuse")
class ReusePinProvider(BaseProvider):
    """A provider that reuses preferred pins if possible.

    This is used to implement "add", "remove", and "reuse upgrade",
    where already-pinned candidates in lockfile should be preferred.
    """

    def __init__(self, *args: Any, tracked_names: Iterable[str], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.tracked_names = set(tracked_names)

    def get_reuse_candidate(self, identifier: str, requirement: Requirement | None) -> Candidate | None:
        bare_name = strip_extras(identifier)[0]
        if bare_name in self.tracked_names or identifier not in self.locked_candidates:
            return None
        pin = self.locked_candidates[identifier]
        if requirement is not None:
            pin.req = requirement
        return pin

    def find_matches(
        self,
        identifier: str,
        requirements: Mapping[str, Iterator[Requirement]],
        incompatibilities: Mapping[str, Iterator[Candidate]],
    ) -> Callable[[], Iterator[Candidate]]:
        super_find = super().find_matches(identifier, requirements, incompatibilities)

        def matches_gen() -> Iterator[Candidate]:
            requested_req = next(filter(lambda r: r.is_named, requirements[identifier]), None)
            pin = self.get_reuse_candidate(identifier, requested_req)
            if pin is not None:
                incompat = list(incompatibilities[identifier])
                pin._preferred = True  # type: ignore[attr-defined]
                if pin not in incompat and all(self.is_satisfied_by(r, pin) for r in requirements[identifier]):
                    yield pin
            yield from super_find()

        return matches_gen


@register_provider("eager")
class EagerUpdateProvider(ReusePinProvider):
    """A specialized provider to handle an "eager" upgrade strategy.

    An eager upgrade tries to upgrade not only packages specified, but also
    their dependencies (recursively). This contrasts to the "only-if-needed"
    default, which only promises to upgrade the specified package, and
    prevents touching anything else if at all possible.

    The provider is implemented as to keep track of all dependencies of the
    specified packages to upgrade, and free their pins when it has a chance.
    """

    def get_reuse_candidate(self, identifier: str, requirement: Requirement | None) -> Candidate | None:
        if identifier in self.tracked_names:
            # If this is a tracked package, don't reuse its pinned version, so it can be upgraded.
            return None
        return super().get_reuse_candidate(identifier, requirement)

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


@register_provider("reuse-installed")
class ReuseInstalledProvider(ReusePinProvider):
    """A provider that reuses installed packages if possible."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.installed = self.repository.environment.get_working_set()

    def get_reuse_candidate(self, identifier: str, requirement: Requirement | None) -> Candidate | None:
        key = strip_extras(identifier)[0]
        if key not in self.installed or requirement is None:
            return super().get_reuse_candidate(identifier, requirement)
        else:
            dist = self.installed[key]
            return Candidate(requirement, name=dist.metadata["Name"], version=dist.metadata["Version"])
