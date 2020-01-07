import os
from typing import Optional, Any, Dict, List

from distlib.database import EggInfoDistribution
from distlib.metadata import Metadata
from distlib.wheel import Wheel
from pip_shims import shims
from pkg_resources import safe_extra

from pdm.context import context
from pdm.exceptions import WheelBuildError, RequirementError
from pdm.utils import cached_property, create_tracked_tempdir
from pdm.models.markers import split_marker_element, Marker
from pdm.models.requirements import Requirement

vcs = shims.VcsSupport()


def get_sdist(ireq: shims.InstallRequirement) -> Optional[EggInfoDistribution]:
    egg_info = ireq.egg_info_path
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

    def __init__(self, req, repository, name=None, version=None, link=None):
        self.req = req
        self.repository = repository
        self.name = name
        self.version = version
        if link is None:
            link = self.ireq.link
        self.link = link

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
            ireq.run_egg_info()
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
        return f"<Candidate {self.name} {self.link.url}>"

    def _make_pip_wheel_args(self) -> Dict[str, Any]:
        src_dir = self.ireq.source_dir or get_source_dir()
        if self.req.editable:
            self.build_dir = src_dir
        else:
            self.build_dir = create_tracked_tempdir(prefix="pdm-build")
        download_dir = context.cache("pkgs")
        download_dir.mkdir(exist_ok=True)
        wheel_download_dir = context.cache("wheels")
        wheel_download_dir.mkdir(exist_ok=True)
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
            # `run_egg_info()` won't work if there is a `req` attribute available.
            self.ireq.req = None
            self.ireq.run_egg_info()
            self.req.name = self.ireq.metadata["Name"]
            self.ireq.req = self.req

        with self.repository.get_finder() as finder:
            kwargs = self._make_pip_wheel_args()
            with shims.make_preparer(
                finder=finder, session=finder.session, **kwargs
            ) as preparer:
                wheel_cache = context.make_wheel_cache()
                builder = shims.WheelBuilder(
                    finder=finder, preparer=preparer, wheel_cache=wheel_cache
                )
                output_dir = create_tracked_tempdir(prefix="pdm-ephem")
                wheel_path = builder._build_one(self.ireq, output_dir)
                if not wheel_path or not os.path.exists(wheel_path):
                    raise WheelBuildError(str(self.ireq))
                self.wheel = Wheel(wheel_path)

    @classmethod
    def from_installation_candidate(cls, candidate, req, repo):
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
            dep_map = self.ireq.get_dist()._build_dep_map()
            for extra, reqs in dep_map.items():
                reqs = [Requirement.from_pkg_requirement(r) for r in reqs]
                if not extra:
                    result.extend(r.as_line() for r in reqs)
                else:
                    new_extra, _, marker = extra.partition(":")
                    if not new_extra.strip() or safe_extra(new_extra.strip()) in extras:
                        marker = Marker(marker) if marker else None
                        for r in reqs:
                            r.marker = marker
                            result.append(r.as_line())
        else:
            for req in metadata.run_requires:
                _r = Requirement.from_line(req)
                if not _r.marker:
                    result.append(req)
                else:
                    elements, rest = split_marker_element(str(_r.marker), "extra")
                    _r.marker = rest
                    if not elements or any(
                        extra == e[1] for extra in extras for e in elements
                    ):
                        result.append(_r.as_line())
        return result
