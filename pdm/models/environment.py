import hashlib
import os
import sys
import sysconfig
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from pip_shims import shims

from distlib.wheel import Wheel
from pdm.exceptions import NoPythonVersion, WheelBuildError
from pdm.models.caches import CandidateInfoCache, HashCache
from pdm.models.specifiers import PySpecSet
from pdm.project import Config
from pdm.types import Source
from pdm.utils import _allow_all_wheels, cached_property, create_tracked_tempdir, get_finder, get_python_version
from pythonfinder import Finder


class Environment:
    def __init__(self, python_requires: PySpecSet, config: Config) -> None:
        self.python_requires = python_requires
        self.config = config

    @property
    def cache_dir(self) -> Path:
        return Path(self.config.get("cache_dir"))

    def cache(self, name: str) -> Path:
        path = self.cache_dir / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def make_wheel_cache(self) -> shims.WheelCache:
        return shims.WheelCache(
            self.cache_dir.as_posix(), shims.FormatControl(set(), set()),
        )

    def make_candidate_info_cache(self) -> CandidateInfoCache:
        python_hash = hashlib.sha1(
            str(self.python_requires).encode()
        ).hexdigest()
        file_name = f"package_meta_{python_hash}.json"
        return CandidateInfoCache(self.cache_dir / file_name)

    def make_hash_cache(self) -> HashCache:
        return HashCache(directory=self.cache("hashes").as_posix())

    @cached_property
    def python_executable(self) -> str:
        """Get the Python interpreter path."""
        if self.config["python"]:
            path = self.config["python"]
            try:
                get_python_version(path)
                return path
            except Exception:
                pass
        else:
            finder = Finder()
            for python in finder.find_all_python_versions():
                version = ".".join(map(str, get_python_version(python.path.as_posix())))
                if self.python_requires.contains(version):
                    return python.path.as_posix()
            if self.python_requires.contains(".".join(map(str, sys.version_info[:3]))):
                return sys.executable
        raise NoPythonVersion(
            "No python matching {} is found on the system.".format(self.python_requires)
        )

    def get_paths(self) -> Dict[str, str]:
        paths = sysconfig.get_paths()
        packages_path = self.packages_path
        paths["platlib"] = paths["purelib"] = (packages_path / "lib").as_posix()
        paths["scripts"] = (packages_path / "bin").as_posix()
        paths["data"] = packages_path.as_posix()
        return paths

    @cached_property
    def packages_path(self) -> Path:
        if self.config.get("packages_path") is not None:
            return self.config.get("packages_path")
        pypackages = (
            self.config.project_root
            / "__pypackages__"
            / ".".join(map(str, get_python_version(self.python_executable)[:2]))
        )
        if not pypackages.exists():
            pypackages.mkdir(parents=True)
        return pypackages

    def _make_pip_wheel_args(self, ireq: shims.InstallRequirement) -> Dict[str, Any]:
        src_dir = ireq.source_dir or self._get_source_dir()
        if ireq.editable:
            build_dir = src_dir
        else:
            build_dir = create_tracked_tempdir(prefix="pdm-build")
        download_dir = self.cache("pkgs")
        wheel_download_dir = self.cache("wheels")
        return {
            "build_dir": build_dir,
            "src_dir": src_dir,
            "download_dir": download_dir.as_posix(),
            "wheel_download_dir": wheel_download_dir.as_posix(),
        }

    def _get_source_dir(self) -> str:
        build_dir = self.packages_path
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

    @contextmanager
    def get_finder(
        self,
        sources: Optional[List[Source]] = None,
        ignore_requires_python: bool = False,
    ) -> shims.PackageFinder:
        sources = sources or []
        requires_python = self.python_requires
        finder = get_finder(
            sources,
            self.cache_dir.as_posix(),
            requires_python.max_major_minor_version() if requires_python else None,
            ignore_requires_python,
        )
        yield finder
        finder.session.close()

    def build_wheel(self, ireq: shims.InstallRequirement) -> Optional[Wheel]:
        """A local candidate has already everything in local, no need to download."""
        kwargs = self._make_pip_wheel_args(ireq)
        with self.get_finder() as finder:
            with _allow_all_wheels():
                # temporarily allow all wheels to get a link.
                ireq.populate_link(finder, False, False)
            if not ireq.editable and not ireq.req.name:
                ireq.source_dir = kwargs["build_dir"]
            else:
                ireq.ensure_has_source_dir(kwargs["build_dir"])
            if ireq.editable and ireq.req.is_local_dir:
                ireq.prepare_metadata()
                return
            download_dir = kwargs["download_dir"]
            if ireq.link.is_wheel:
                download_dir = kwargs["wheel_download_dir"]
            shims.shim_unpack(
                link=ireq.link,
                download_dir=download_dir,
                location=ireq.source_dir,
                session=finder.session,
            )

            if ireq.link.is_wheel:
                return Wheel(
                    (self.cache("wheels") / ireq.link.filename).as_posix()
                )
            # VCS url is unpacked, now build the egg-info
            if ireq.editable and ireq.req.is_vcs:
                ireq.prepare_metadata()
                return

            if not ireq.req.name:
                # Name is not available for a tarball distribution. Get the package name
                # from package's egg info.
                # `prepare_metadata()` won't work if there is a `req` attribute.
                req = ireq.req
                ireq.req = None
                ireq.prepare_metadata()
                req.name = ireq.metadata["Name"]
                ireq.req = req

            with shims.make_preparer(
                finder=finder, session=finder.session, **kwargs
            ) as preparer:
                wheel_cache = self.make_wheel_cache()
                builder = shims.WheelBuilder(preparer=preparer, wheel_cache=wheel_cache)
                output_dir = create_tracked_tempdir(prefix="pdm-ephem")
                wheel_path = builder._build_one(ireq, output_dir)
                if not wheel_path or not os.path.exists(wheel_path):
                    raise WheelBuildError(str(ireq))
                return Wheel(wheel_path)
