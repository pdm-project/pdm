import os
import warnings
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from pip._vendor.pkg_resources import safe_extra
from pip_shims import shims

from distlib.database import EggInfoDistribution
from distlib.metadata import Metadata
from distlib.wheel import Wheel
from pdm.context import context
from pdm.exceptions import ExtrasError, RequirementError, WheelBuildError
from pdm.models.markers import Marker
from pdm.models.requirements import Requirement, filter_requirements_with_extras
from pdm.utils import _allow_all_wheels, cached_property, create_tracked_tempdir

if TYPE_CHECKING:
    from pdm.models.repositories import BaseRepository

vcs = shims.VcsSupport()


def get_sdist(ireq: shims.InstallRequirement) -> Optional[EggInfoDistribution]:
    egg_info = ireq.metadata_directory
    return EggInfoDistribution(egg_info) if egg_info else None


def get_source_dir() -> str:
    build_dir = context.project.packages_root
    if build_dir:
        src_dir = build_dir / "src"
        src_dir.mkdir(exist_ok=True)
        return src_dir.as_posix()
    venv = os.environ.get("VIRTUAL_ENV", None)
    if venv:
        src_dir = os.path.join(venv, "src")
        if os.path.exists(src_dir):
            return src_dir
    return create_tracked_tempdir("pdm-src")


class Candidate:
    """A concrete candidate that can be downloaded and installed."""

    def __init__(
        self,
        req,  # type: Requirement
        repository,  # type: BaseRepository
        name=None,  # type: Optional[str]
        version=None,  # type: Optional[str]
        link=None,  # type: shims.Link
    ):
        # type: (...) -> None
        self.req = req
        self.repository = repository
        self.name = name or self.req.project_name
        self.version = version or self.req.version
        if link is None:
            link = self.ireq.link
        self.link = link
        self.hashes = None  # type: Optional[Dict[str, str]]
        self.marker = None

        self.wheel = None
        self.build_dir = None
        self.metadata = None

    @cached_property
    def ireq(self) -> shims.InstallRequirement:
        return self.req.as_ireq()

    @property
    def is_wheel(self) -> bool:
        return self.link.is_wheel

    @cached_property
    def revision(self) -> str:
        if not self.req.is_vcs:
            raise AttributeError("Non-VCS candidate doesn't have revision attribute")
        return vcs.get_backend(self.req.vcs).get_revision(self.ireq.source_dir)

    def get_metadata(self) -> Optional[Metadata]:
        if self.metadata is not None:
            return self.metadata
        ireq = self.ireq
        if ireq.editable:
            if not self.req.is_local_dir and not self.req.is_vcs:
                raise RequirementError(
                    "Editable installation is only supported for "
                    "local directory and VCS location."
                )
            ireq.prepare_metadata()
            sdist = get_sdist(ireq)
            self.metadata = sdist.metadata if sdist else None
        else:
            if not self.wheel:
                self._build_wheel()
            self.metadata = self.wheel.metadata
        if not self.name:
            self.name = self.metadata.name
            self.req.name = self.name
        if not self.version:
            self.version = self.metadata.version
        return self.metadata

    def __repr__(self) -> str:
        return f"<Candidate {self.name} {self.version}>"

    def _make_pip_wheel_args(self) -> Dict[str, Any]:
        src_dir = self.ireq.source_dir or get_source_dir()
        if self.req.editable:
            self.build_dir = src_dir
        else:
            self.build_dir = create_tracked_tempdir(prefix="pdm-build")
        download_dir = context.cache("pkgs")
        wheel_download_dir = context.cache("wheels")
        return {
            "build_dir": self.build_dir,
            "src_dir": src_dir,
            "download_dir": download_dir.as_posix(),
            "wheel_download_dir": wheel_download_dir.as_posix(),
        }

    def prepare_source(self) -> None:
        """A local candidate has already everything in local, no need to download."""
        kwargs = self._make_pip_wheel_args()
        with self.repository.get_finder() as finder:
            with _allow_all_wheels():
                # temporarily allow all wheels to get a link.
                self.ireq.populate_link(finder, False, False)
            if not self.req.editable and not self.req.name:
                self.ireq.source_dir = kwargs["build_dir"]
            else:
                self.ireq.ensure_has_source_dir(kwargs["build_dir"])
            if self.req.editable and self.req.is_local_dir:
                return
            download_dir = kwargs["download_dir"]
            if self.is_wheel:
                download_dir = kwargs["wheel_download_dir"]
            shims.shim_unpack(
                link=self.link,
                download_dir=download_dir,
                location=self.ireq.source_dir,
                session=finder.session,
            )

    def _build_wheel(self) -> None:
        if self.is_wheel:
            self.wheel = Wheel(
                (context.cache("wheels") / self.link.filename).as_posix()
            )
            return
        if not self.req.name:
            # Name is not available for a tarball distribution. Get the package name
            # from package's egg info.
            # `prepare_metadata()` won't work if there is a `req` attribute available.
            self.ireq.req = None
            self.ireq.prepare_metadata()
            self.req.name = self.ireq.metadata["Name"]
            self.ireq.req = self.req

        with self.repository.get_finder() as finder:
            kwargs = self._make_pip_wheel_args()
            with shims.make_preparer(
                finder=finder, session=finder.session, **kwargs
            ) as preparer:
                wheel_cache = context.make_wheel_cache()
                builder = shims.WheelBuilder(preparer=preparer, wheel_cache=wheel_cache)
                output_dir = create_tracked_tempdir(prefix="pdm-ephem")
                wheel_path = builder._build_one(self.ireq, output_dir)
                if not wheel_path or not os.path.exists(wheel_path):
                    raise WheelBuildError(str(self.ireq))
                self.wheel = Wheel(wheel_path)

    @classmethod
    def from_installation_candidate(
        cls,
        candidate,  # type: shims.InstallationCandidate
        req,  # type: Requirement
        repo,  # type: BaseRepository
    ):
        # type: (...) -> Candidate
        inst = cls(
            req,
            repo,
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
            "section": self.req.from_section,
            "version": str(self.version),
            "extras": sorted(self.req.extras or ()),
            "marker": str(self.marker) if self.marker else None,
            "editable": self.req.editable,
        }
        if self.req.is_vcs:
            result.update({self.req.vcs: self.req.url, "revision": self.revision})
        if not self.req.is_named:
            result.update(url=self.req.url)
        return {k: v for k, v in result.items() if v}
