from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from pip._vendor.pkg_resources import safe_extra
from pip_shims import shims

from distlib.database import EggInfoDistribution
from distlib.metadata import Metadata
from distlib.wheel import Wheel
from pdm.context import context
from pdm.exceptions import ExtrasError, RequirementError
from pdm.models.markers import Marker
from pdm.models.requirements import Requirement, filter_requirements_with_extras
from pdm.utils import cached_property

if TYPE_CHECKING:
    from pdm.models.environment import Environment

vcs = shims.VcsSupport()


def get_sdist(egg_info) -> Optional[EggInfoDistribution]:
    return EggInfoDistribution(egg_info) if egg_info else None


def identify(req: Union[Candidate, Requirement]) -> Optional[str]:
    if isinstance(req, Candidate):
        req = req.req
    if req.key is None:
        # Name attribute may be None for local tarballs.
        # It will be picked up in the following get_dependencies calls.
        return None
    extras = "[{}]".format(",".join(sorted(req.extras))) if req.extras else ""
    return req.key + extras


class Candidate:
    """A concrete candidate that can be downloaded and installed."""

    def __init__(
        self,
        req,  # type: Requirement
        environment,  # type: Environment
        name=None,  # type: Optional[str]
        version=None,  # type: Optional[str]
        link=None,  # type: shims.Link
    ):
        # type: (...) -> None
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
    def ireq(self) -> shims.InstallRequirement:
        return self.req.as_ireq()

    def __eq__(self, other: "Candidate") -> bool:
        if self.req.is_named:
            return self.name == other.name and self.version == other.version
        return self.name == other.name and self.link == other.link

    @cached_property
    def revision(self) -> str:
        if not self.req.is_vcs:
            raise AttributeError("Non-VCS candidate doesn't have revision attribute")
        return vcs.get_backend(self.req.vcs).get_revision(self.ireq.source_dir)

    def get_metadata(self) -> Optional[Metadata]:
        if self.metadata is not None:
            return self.metadata
        ireq = self.ireq
        built = self.environment.build(ireq, self.hashes)
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
        candidate,  # type: shims.InstallationCandidate
        req,  # type: Requirement
        environment,  # type: Environment
    ):
        # type: (...) -> Candidate
        inst = cls(
            req,
            environment,
            name=candidate.project,
            version=candidate.version,
            link=candidate.link,
        )
        return inst

    def get_dependencies_from_metadata(self) -> List[str]:
        extras = self.req.extras or ()
        metadata = self.get_metadata()
        result = []
        if self.req.editable:
            if not metadata:
                return result
            extras_in_metadata = []
            dep_map = self.ireq.get_dist()._build_dep_map()
            for extra, reqs in dep_map.items():
                reqs = [Requirement.from_pkg_requirement(r) for r in reqs]
                if not extra:
                    result.extend(r.as_line() for r in reqs)
                else:
                    new_extra, _, marker = extra.partition(":")
                    extras_in_metadata.append(new_extra.strip())
                    if not new_extra.strip() or safe_extra(new_extra.strip()) in extras:
                        marker = Marker(marker) if marker else None
                        for r in reqs:
                            r.marker = marker
                            result.append(r.as_line())
            extras_not_found = [e for e in extras if e not in extras_in_metadata]
            if extras_not_found:
                warnings.warn(ExtrasError(extras_not_found), stacklevel=2)
        else:
            result = filter_requirements_with_extras(metadata.run_requires, extras)
        return result

    @property
    def requires_python(self) -> str:
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

    def as_lockfile_entry(self) -> Dict[str, Any]:
        result = {
            "name": self.name,
            "sections": sorted(self.sections),
            "version": str(self.version),
            "extras": sorted(self.req.extras or ()),
            "marker": str(self.marker) if self.marker else None,
            "editable": self.req.editable,
        }
        if self.req.is_vcs:
            result.update({self.req.vcs: self.req.repo, "revision": self.revision})
        elif not self.req.is_named:
            if self.req.path:
                result.update(path=self.req.str_path)
            else:
                result.update(url=self.req.url)
        return {k: v for k, v in result.items() if v}

    def format(self) -> str:
        return (
            f"{context.io.green(self.name, bold=True)} "
            f"{context.io.yellow(str(self.version))}"
        )
