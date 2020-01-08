from contextlib import contextmanager
from typing import List, Tuple

import pip_shims

from pdm.context import context
from pdm.models.candidates import Candidate
from pdm.models.requirements import Requirement
from pdm.models.specifiers import PySpecSet
from pdm.types import Source
from pdm.utils import get_finder


class BaseRepository:
    def __init__(self, sources: List[Source]) -> None:
        self.sources = sources

    @contextmanager
    def get_finder(self) -> pip_shims.PackageFinder:
        finder = get_finder(self.sources, context.cache_dir.as_posix())
        yield finder
        finder.session.close()

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
        if self.requirement.is_named:
            return self._find_named_matches(
                requirement, requires_python, allow_prereleases
            )
        else:
            return [Candidate(requirement, self)]

    def _find_named_matches(
        self,
        requirement: Requirement,
        requires_python: PySpecSet,
        allow_prereleases: bool = False,
    ) -> List[Candidate]:
        """Find candidates of the given NamedRequirement. Let it to be implemented in
        subclasses.
        """
        raise NotImplementedError

    def _get_dependencies_from_cache(
        self, candidate: Candidate
    ) -> Tuple[List[str], str]:
        pass

    def _get_dependencies_from_metadata(
        self, candidate: Candidate
    ) -> Tuple[List[str], str]:
        candidate.prepare_source()
        deps = candidate.get_dependencies_from_metadata()
        return deps


class PyPIRepository(BaseRepository):
    def _get_dependencies_from_json(
        self, candidate: Candidate
    ) -> Tuple[List[str], str]:
        pass


class MockRepository(BaseRepository):
    pass
