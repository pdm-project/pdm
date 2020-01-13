from typing import Dict, List, Optional, Union

from pdm.models.candidates import Candidate
from pdm.models.repositories import BaseRepository
from pdm.models.requirements import Requirement
from pdm.models.specifiers import PySpecSet
from resolvelib.providers import AbstractProvider
from resolvelib.resolvers import RequirementInformation


class RepositoryProvider(AbstractProvider):
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
        )  # type: Dict[Optional[str], Dict[str, List[Requirement]]]

    def identify(self, req: Union[Requirement, Candidate]) -> Optional[str]:
        if isinstance(req, Candidate):
            req = req.req
        if req.key is None:
            # Name attribute may be None for local tarballs.
            # It will be picked up in the following get_dependencies calls.
            return None
        extras = "[{}]".format(",".join(sorted(req.extras))) if req.extras else ""
        return req.key + extras

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
