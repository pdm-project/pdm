from pathlib import Path
from typing import Optional

from distlib.database import EggInfoDistribution
from distlib.metadata import Metadata
from pip_shims import InstallRequirement
from pkg_resources import safe_name


def get_egg_info(ireq: InstallRequirement) -> Optional[str]:
    root = Path(ireq.setup_py_dir)
    name = safe_name(ireq.name)
    if (root / f"{name}.egg-info").is_dir():
        return (root / f"{name}.egg-info").as_posix()


def get_sdist(ireq: InstallRequirement) -> Optional[EggInfoDistribution]:
    egg_info = get_egg_info(ireq)
    return EggInfoDistribution(egg_info) if egg_info else None


class Candidate:
    """A concrete candidate that can be downloaded and installed."""

    @property
    def is_local(self) -> bool:
        return isinstance(self, LocalDirCandidate)


class LocalDirCandidate(Candidate):
    def __init__(self, location: str, req):
        self.location = Path(location).absolute()
        self.req = req
        self._source_ready = True
        self.wheel = None

    @property
    def source_dir(self) -> str:
        return self.path.as_posix()

    def prepare_source(self) -> None:
        pass

    def get_metadata(self) -> Optional[Metadata]:
        if not self._source_ready:
            self.prepare_source()
        ireq = self.req.as_ireq()
        if ireq.editable:
            ireq.run_egg_info()
            sdist = get_sdist(ireq)
            return sdist.metadata if sdist else None


class FileCandidate(Candidate):
    pass


class VcsCandidate(LocalDirCandidate):
    pass
