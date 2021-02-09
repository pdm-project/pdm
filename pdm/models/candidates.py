from __future__ import annotations

import functools
import warnings
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence

from distlib.database import EggInfoDistribution
from distlib.wheel import Wheel
from pip._vendor.pkg_resources import safe_extra

from pdm.exceptions import ExtrasError, RequirementError
from pdm.iostream import stream
from pdm.models import pip_shims
from pdm.models.markers import Marker
from pdm.models.requirements import Requirement, filter_requirements_with_extras
from pdm.utils import cached_property, path_replace

if TYPE_CHECKING:
    from distlib.metadata import Metadata

    from pdm.models.environment import Environment

vcs = pip_shims.VcsSupport()


def get_sdist(egg_info) -> Optional[EggInfoDistribution]:
    """Get a distribution from egg_info directory."""
    return EggInfoDistribution(egg_info) if egg_info else None


def _patch_version_parsing():
    """Monkey patches the version parsing to allow empty parts in version constraint
    list.
    """
    from distlib.version import VersionScheme
    from packaging.requirements import InvalidRequirement
    from packaging.requirements import Requirement as PRequirement

    def is_valid_matcher(self, s):
        try:
            PRequirement(s)
        except InvalidRequirement:
            return False
        return True

    VersionScheme.is_valid_matcher = is_valid_matcher


_patch_version_parsing()
del _patch_version_parsing


@functools.lru_cache(128)
def get_requirements_from_dist(
    dist: EggInfoDistribution, extras: Sequence[str]
) -> List[str]:
    """Get requirements of a distribution, with given extras."""
    extras_in_metadata = []
    result = []
    dep_map = dist._build_dep_map()
    for extra, reqs in dep_map.items():
        reqs = [Requirement.from_pkg_requirement(r) for r in reqs]
        if not extra:
            # requirements without extras are always required.
            result.extend(r.as_line() for r in reqs)
        else:
            new_extra, _, marker = extra.partition(":")
            extras_in_metadata.append(new_extra.strip())
            # Only include requirements that match one of extras.
            if not new_extra.strip() or safe_extra(new_extra.strip()) in extras:
                marker = Marker(marker) if marker else None
                for r in reqs:
                    r.marker = marker
                    result.append(r.as_line())
    extras_not_found = [e for e in extras if e not in extras_in_metadata]
    if extras_not_found:
        warnings.warn(ExtrasError(extras_not_found), stacklevel=2)
    return result


class Candidate:
    """A concrete candidate that can be downloaded and installed.
    A candidate comes from the PyPI index of a package, or from the requirement itself
    (for file or VCS requirements). Each candidate has a name, version and several
    dependencies together with package metadata.
    """

    def __init__(
        self,
        req,  # type: Requirement
        environment,  # type: Environment
        name=None,  # type: Optional[str]
        version=None,  # type: Optional[str]
        link=None,  # type: pip_shims.Link
    ):
        # type: (...) -> None
        """
        :param req: the requirement that produces this candidate.
        :param environment: the bound environment instance.
        :param name: the name of the candidate.
        :param version: the version of the candidate.
        :param link: the file link of the candidate.
        """
        self.req = req
        self.environment = environment
        self.name = name or self.req.project_name
        self.version = version or self.req.version
        if link is None and self.req:
            link = self.ireq.link
        self.link = link
        self.hashes = None  # type: Optional[Dict[str, str]]
        self.marker = None
        self.sections = []
        self._requires_python = None

        self.wheel = None
        self.metadata = None

    def __hash__(self):
        return hash((self.name, self.version))

    @cached_property
    def ireq(self) -> pip_shims.InstallRequirement:
        return self.req.as_ireq()

    def identify(self) -> str:
        return self.req.identify()

    def __eq__(self, other: "Candidate") -> bool:
        if self.req.is_named:
            return self.name == other.name and self.version == other.version
        return self.name == other.name and self.link == other.link

    @cached_property
    def revision(self) -> str:
        if not self.req.is_vcs:
            raise AttributeError("Non-VCS candidate doesn't have revision attribute")
        return vcs.get_backend(self.req.vcs).get_revision(self.ireq.source_dir)

    def get_metadata(self, allow_all_wheels: bool = True) -> Optional[Metadata]:
        """Get the metadata of the candidate.
        For editable requirements, egg info are produced, otherwise a wheel is built.
        """
        if self.metadata is not None:
            return self.metadata
        ireq = self.ireq
        if self.link and not ireq.link:
            ireq.link = self.link
        built = self.environment.build(ireq, self.hashes, allow_all_wheels)
        if self.req.editable:
            if not self.req.is_local_dir and not self.req.is_vcs:
                raise RequirementError(
                    "Editable installation is only supported for "
                    "local directory and VCS location."
                )
            sdist = get_sdist(built)
            self.metadata = sdist.metadata if sdist else None
        else:
            # It should be a wheel path.
            self.wheel = Wheel(built)
            self.metadata = self.wheel.metadata
        if not self.name:
            self.name = self.metadata.name
            self.req.name = self.name
        if not self.version:
            self.version = self.metadata.version
        self.link = ireq.link
        return self.metadata

    def __repr__(self) -> str:
        return f"<Candidate {self.name} {self.version}>"

    @classmethod
    def from_installation_candidate(
        cls,
        candidate,  # type: pip_shims.InstallationCandidate
        req,  # type: Requirement
        environment,  # type: Environment
    ):
        # type: (...) -> Candidate
        """Build a candidate from pip's InstallationCandidate."""
        inst = cls(
            req,
            environment,
            name=candidate.name,
            version=candidate.version,
            link=candidate.link,
        )
        return inst

    def get_dependencies_from_metadata(self) -> List[str]:
        """Get the dependencies of a candidate from metadata."""
        extras = self.req.extras or ()
        metadata = self.get_metadata()
        if self.req.editable:
            if not metadata:
                return []
            return get_requirements_from_dist(self.ireq.get_dist(), extras)
        else:
            return filter_requirements_with_extras(metadata.run_requires, extras)

    @property
    def requires_python(self) -> str:
        """The Python version constraint of the candidate."""
        if self._requires_python is not None:
            return self._requires_python
        requires_python = self.link.requires_python or ""
        if not requires_python and self.metadata:
            # For candidates fetched from PyPI simple API, requires_python is not
            # available yet. Just allow all candidates, and dismatching candidates
            # will be filtered out during resolving process.
            try:
                requires_python = self.metadata.requires_python
            except AttributeError:
                requires_python = getattr(
                    self.metadata._legacy, "requires_python", "UNKNOWN"
                )
            if not requires_python or requires_python == "UNKNOWN":
                requires_python = ""
        if requires_python.isdigit():
            requires_python = f">={requires_python},<{int(requires_python) + 1}"
        return requires_python

    @requires_python.setter
    def requires_python(self, value: str) -> None:
        self._requires_python = value

    def as_lockfile_entry(self) -> Dict[str, Any]:
        """Build a lockfile entry dictionary for the candidate."""
        result = {
            "name": self.name,
            "sections": sorted(self.sections),
            "version": str(self.version),
            "extras": sorted(self.req.extras or ()),
            "marker": str(self.marker).replace('"', "'") if self.marker else None,
            "editable": self.req.editable,
        }
        project_root = self.environment.project.root.as_posix()
        if self.req.is_vcs:
            result.update({self.req.vcs: self.req.repo, "revision": self.revision})
        elif not self.req.is_named:
            if self.req.is_file_or_url and self.req.is_local_dir:
                result.update(path=path_replace(project_root, ".", self.req.str_path))
            else:
                result.update(
                    url=path_replace(
                        project_root.lstrip("/"), "${PROJECT_ROOT}", self.req.url
                    )
                )
        return {k: v for k, v in result.items() if v}

    def format(self) -> str:
        """Format for output."""
        return (
            f"{stream.green(self.name, bold=True)} "
            f"{stream.yellow(str(self.version))}"
        )
