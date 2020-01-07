from resolvelib.providers import AbstractProvider
from requirementslib import Requirement
from pdm.models.repositories import BaseRepository


class RepositoryProvider(AbstractProvider):
    def __init__(self, repository: BaseRepository) -> None:
        self.repository = repository

    def identify(self, requirement: Requirement) -> str:
        return requirement.key
