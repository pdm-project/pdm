from resolvelib.providers import AbstractProvider
from requirementslib import Requirement
from pdm.models.repositories import BaseRepository
from typing import List


class RepositoryProvider(AbstractProvider):
    def __init__(self, repositories: List[BaseRepository]) -> None:
        self.repositories = repositories

    def identify(self, requirement: Requirement) -> str:
        return requirement.key
