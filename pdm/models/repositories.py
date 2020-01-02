from pdm.types import Source


class BaseRepository:
    def __init__(self, source: Source) -> None:
        self.source = source


class PyPIRepository(BaseRepository):
    pass
