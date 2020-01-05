from typing import Optional, TYPE_CHECKING

from distlib.database import EggInfoDistribution
from distlib.metadata import Metadata
from pip_shims import InstallRequirement
from pip._internal.exceptions import InstallationError

if TYPE_CHECKING:
    from pdm.models.requirements import Requirement
    from pdm.models.repositories import BaseRepository


def get_sdist(ireq: InstallRequirement) -> Optional[EggInfoDistribution]:
    try:
        egg_info = ireq.egg_info_path
    except InstallationError:
        ireq.run_egg_info()
        egg_info = ireq.egg_info_path
    return EggInfoDistribution(egg_info) if egg_info else None


class Candidate:
    """A concrete candidate that can be downloaded and installed."""

    def __init__(self, req, repository=None):
        # type: (Requirement, Optional[BaseRepository]) -> None
        self.req = req
        self.repository = repository
        self.wheel = None

    def get_metadata(self) -> Optional[Metadata]:
        ireq = self.req.as_ireq()
        if ireq.editable:
            sdist = get_sdist(ireq)
            return sdist.metadata if sdist else None
        else:
            if not self.wheel:
                self._build_wheel()
            return self.wheel.meta

    def _build_wheel(self) -> None:
        pass


class LocalCandidate(Candidate):
    def __init__(self, req, repository=None):
        # type: (Requirement, Optional[BaseRepository]) -> None
        super().__init__(req, repository)
        self.location = self.req.path.absolute()

    def prepare_sources(self) -> None:
        """A local candidate has already everything in local, no need to download."""
        pass

    @property
    def source_dir(self) -> str:
        return self.location.as_posix()


class RemoteCandidate(LocalCandidate):
    pass


class VcsCandidate(LocalCandidate):
    pass
