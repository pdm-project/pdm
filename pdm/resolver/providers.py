from typing import Dict, Iterable, List, Optional, Union

from pdm.models.candidates import Candidate, identify
from pdm.models.repositories import BaseRepository
from pdm.models.requirements import Requirement
from pdm.models.specifiers import PySpecSet
from pdm.resolver.resolvers import RequirementInformation


class BaseProvider:
    def __init__(
        self,
        repository: BaseRepository,
        requires_python: PySpecSet,
        allow_prereleases: Optional[bool] = None,
    ) -> None:
        self.repository = repository
        self.requires_python = requires_python  # Root python_requires value
        self.allow_prereleases = allow_prereleases  # Root allow_prereleases value
        self.requires_python_collection = {
            None: requires_python
        }  # type: Dict[Optional[str], PySpecSet]
        self.summary_collection = {}  # type: Dict[str, str]
        self.fetched_dependencies = (
            {}
        )  # type: Dict[str, Dict[str, List[Requirement]]]

    def identify(self, req: Union[Requirement, Candidate]) -> Optional[str]:
        return identify(req)

    def get_preference(
        self,
        resolution: Candidate,
        candidates: List[Candidate],
        information: List[RequirementInformation],
    ) -> int:
        return len(candidates)

    def find_matches(self, requirement: Requirement) -> List[Candidate]:
        return self.repository.find_matches(
            requirement, self.requires_python, self.allow_prereleases
        )

    def is_satisfied_by(self, requirement: Requirement, candidate: Candidate) -> bool:
        if not candidate.version or not requirement.is_named:
            return True
        return requirement.specifier.contains(
            candidate.version
        ) and self.requires_python.is_subset(candidate.requires_python)

    def get_dependencies(self, candidate: Candidate) -> List[Requirement]:
        deps, requires_python, summary = self.repository.get_dependencies(candidate)

        # Filter out incompatible dependencies(e.g. functools32) early so that
        # we don't get errors when building wheels.
        valid_deps = [
            dep
            for dep in deps
            if not (
                dep.requires_python & requires_python & self.requires_python
            ).is_impossible
        ]

        candidate_key = self.identify(candidate.req)
        self.fetched_dependencies[candidate_key] = {
            self.identify(r): r for r in valid_deps
        }
        self.summary_collection[candidate_key] = summary
        self.requires_python_collection[candidate_key] = requires_python
        return valid_deps

    def get_hashes(self, candidate) -> Optional[Dict[str, str]]:
        return self.repository.get_hashes(candidate)


class ReusePinProvider(BaseProvider):
    """A provider that reuses preferred pins if possible.

    This is used to implement "add", "remove", and "reuse upgrade",
    where already-pinned candidates in lockfile should be preferred.
    """
    def __init__(
        self, preferred_pins: Dict[str, Candidate], tracked_names: Iterable[str], *args
    ):
        super().__init__(*args)
        self.preferred_pins = preferred_pins
        self.tracked_names = set(tracked_names)

    def is_satisfied_by(self, requirement, candidate):
        # If this is a tracking package, tell the resolver out of using the
        # preferred pin, and into a "normal" candidate selection process.
        if getattr(candidate, "_preferred", False):
            return True
        return super().is_satisfied_by(
            requirement, candidate,
        )

    def find_matches(self, requirement: Requirement) -> List[Candidate]:
        result = super().find_matches(requirement)
        ident = self.identify(requirement)
        if ident not in self.tracked_names and ident in self.preferred_pins:
            pin = self.preferred_pins[ident]
            pin._preferred = True
            result.append(pin)
        return result


class EagerUpdateProvider(ReusePinProvider):
    """A specialized provider to handle an "eager" upgrade strategy.

        An eager upgrade tries to upgrade not only packages specified, but also
        their dependencies (recursively). This contrasts to the "only-if-needed"
        default, which only promises to upgrade the specified package, and
        prevents touching anything else if at all possible.

        The provider is implemented as to keep track of all dependencies of the
        specified packages to upgrade, and free their pins when it has a chance.
        """

    def is_satisfied_by(self, requirement, candidate):
        # If this is a tracking package, tell the resolver out of using the
        # preferred pin, and into a "normal" candidate selection process.
        if (
            self.identify(requirement) in self.tracked_names
            and getattr(candidate, "_preferred", False)
        ):
            return False
        return super().is_satisfied_by(
            requirement, candidate,
        )

    def get_dependencies(self, candidate):
        # If this package is being tracked for upgrade, remove pins of its
        # dependencies, and start tracking these new packages.
        dependencies = super().get_dependencies(candidate)
        if self.identify(candidate) in self.tracked_names:
            for dependency in dependencies:
                name = self.identify(dependency)
                self.tracked_names.add(name)
        return dependencies

    def get_preference(self, resolution, candidates, information):
        # Resolve tracking packages so we have a chance to unpin them first.
        name = self.identify(candidates[0])
        if name in self.tracked_names:
            return -1
        return len(candidates)
