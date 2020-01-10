from resolvelib.providers import AbstractProvider
from pdm.models.requirements import Requirement
from pdm.models.repositories import BaseRepository
from pdm.models.specifiers import PySpecSet
from pdm.models.candidates import Candidate
from resolvelib.resolvers import RequirementInformation
from typing import List, Union, Optional, Dict


class RepositoryProvider(AbstractProvider):

    def __init__(
        self, repository: BaseRepository, requires_python: PySpecSet, allow_prereleases: Optional[bool] = None
    ) -> None:
        self.repository = repository
        self.requires_python = requires_python  # Root python_requires value
        self.allow_prereleases = allow_prereleases  # Root allow_prereleases value
        self.requires_python_collection = {None: requires_python}  # type: Dict[Optional[str], PySpecSet]
        self.summary_collection = {}  # type: Dict[str, str]
        self.fetched_dependencies = {}  # type: Dict[Optional[str], Dict[str, List[Requirement]]]

    def identify(self, req: Union[Requirement, Candidate]) -> str:
        if isinstance(req, Candidate):
            req = req.req
        extras = "[{}]".format(','.join(sorted(req.extras))) if req.extras else ""
        return req.key + extras

    def get_preference(
        self,
        resolution: Candidate,
        candidates: List[Candidate],
        information: List[RequirementInformation]
    ) -> int:
        return len(candidates)

    def find_matches(self, requirement: Requirement) -> List[Candidate]:
        return self.repository.find_matches(requirement, self.requires_python, self.allow_prereleases)

    def is_satisfied_by(self, requirement: Requirement, candidate: Candidate) -> bool:
        if not candidate.version:
            return True
        return (
            requirement.specifier.contains(candidate.version)
            and self.requires_python.is_subset(candidate.requires_python)
        )

    def get_dependencies(self, candidate: Candidate) -> List[Requirement]:
        deps, requires_python, summary = self.repository.get_dependencies(candidate)
        candidate_key = self.identify(candidate.req)
        self.fetched_dependencies[candidate_key] = {
            self.identify(r): r for r in deps
        }
        self.summary_collection[candidate_key] = summary
        self.requires_python_collection[candidate_key] = requires_python
        return deps
