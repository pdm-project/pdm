from typing import List, Tuple

from pdm.types import Source
from pdm.models.candidates import Candidate
from pdm.models.requirements import Requirement
from pdm.models.specifiers import PySpecSet


class BaseRepository:
    def __init__(self, source: Source, cache_dir: str) -> None:
        self.source = source
        self.cache_dir = cache_dir

    def match_index(self, requirement: Requirement) -> bool:
        return requirement.index is None or requirement.index == self.source["name"]

    def get_dependencies(
        self, candidate: Candidate
    ) -> Tuple[List[Requirement], PySpecSet]:
        raise NotImplementedError

    def find_matches(
        self,
        requirement: Requirement,
        requires_python: PySpecSet,
        allow_prereleases: bool = False,
    ) -> List[Candidate]:
        raise NotImplementedError

    def _get_dependencies_from_cache(
        self, candidate: Candidate
    ) -> Tuple[List[Requirement], PySpecSet]:
        pass

    def _get_dependencies_from_local(
        self, candidate: Candidate
    ) -> Tuple[List[Requirement], PySpecSet]:
        if not candidate.is_local:
            return [], PySpecSet()


class PyPIRepository(BaseRepository):
    def _get_dependencies_from_json(
        self, candidate: Candidate
    ) -> Tuple[List[Requirement], PySpecSet]:
        pass

    def _get_dependencies_from_simple(
        self, candidate: Candidate
    ) -> Tuple[List[Requirement], PySpecSet]:
        pass


class MockRepository(BaseRepository):
    pass
