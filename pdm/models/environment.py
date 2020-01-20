from __future__ import annotations

import os
import sys
import sysconfig
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from pip._internal.req import req_uninstall
from pip._internal.utils import misc
from pip._vendor import pkg_resources
from pip_shims import shims

from distlib.wheel import Wheel
from pdm.context import context
from pdm.exceptions import NoPythonVersion, WheelBuildError
from pdm.utils import (
    _allow_all_wheels,
    cached_property,
    convert_hashes,
    create_tracked_tempdir,
    get_finder,
    get_python_version,
    get_pep508_environment,
)
from pythonfinder import Finder
from vistir.contextmanagers import temp_environ
from vistir.path import normalize_path

if TYPE_CHECKING:
    from pdm.models.specifiers import PySpecSet
    from pdm.project.config import Config
    from pdm._types import Source


class Environment:
    def __init__(self, python_requires: PySpecSet, config: Config) -> None:
        self.python_requires = python_requires
        self.config = config

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
        scripts = "Scripts" if os.name == "nt" else "bin"
        packages_path = self.packages_path
        paths["platlib"] = paths["purelib"] = (packages_path / "lib").as_posix()
        paths["scripts"] = (packages_path / scripts).as_posix()
        paths["data"] = paths["prefix"] = packages_path.as_posix()
        paths["include"] = paths["platinclude"] = paths["headers"] = (
            packages_path / "include"
        ).as_posix()
        return paths

    @contextmanager
    def activate(self):
        paths = self.get_paths()
        with temp_environ():
            old_paths = os.getenv("PYTHONPATH")
            if old_paths:
                new_paths = os.pathsep.join([paths["platlib"], old_paths])
            else:
                new_paths = paths["platlib"]
            os.environ["PYTHONPATH"] = new_paths
            python_root = os.path.dirname(self.python_executable)
            os.environ["PATH"] = os.pathsep.join(
                [python_root, paths["scripts"], os.environ["PATH"]]
            )
            working_set = self.get_working_set()
            _old_ws = pkg_resources.working_set
            pkg_resources.working_set = working_set
            # HACK: Replace the is_local with environment version so that packages can
            # be removed correctly.
            _is_local = misc.is_local
            misc.is_local = req_uninstall.is_local = self.is_local
            yield
            misc.is_local = req_uninstall.is_local = _is_local
            pkg_resources.working_set = _old_ws

    def is_local(self, path) -> bool:
        return normalize_path(path).startswith(
            normalize_path(self.packages_path.as_posix())
        )

    @cached_property
    def packages_path(self) -> Path:
        if self.config.get("packages_path") is not None:
            return self.config.get("packages_path")
        pypackages = (
            self.config.project_root
            / "__pypackages__"
            / ".".join(map(str, get_python_version(self.python_executable)[:2]))
        )
        scripts = "Scripts" if os.name == "nt" else "bin"
        for subdir in [scripts, "include", "lib"]:
            pypackages.joinpath(subdir).mkdir(exist_ok=True, parents=True)
        return pypackages

    def _make_pip_wheel_args(self, ireq: shims.InstallRequirement) -> Dict[str, Any]:
        src_dir = ireq.source_dir or self._get_source_dir()
        if ireq.editable:
            build_dir = src_dir
        else:
            build_dir = create_tracked_tempdir(prefix="pdm-build")
        download_dir = context.cache("pkgs")
        wheel_download_dir = context.cache("wheels")
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
        python_version = get_python_version(self.python_executable)[:2]
        finder = get_finder(
            sources,
            context.cache_dir.as_posix(),
            python_version,
            ignore_requires_python,
        )
        yield finder
        finder.session.close()

    def build_wheel(
        self, ireq: shims.InstallRequirement, hashes: Optional[Dict[str, str]] = None
    ) -> Optional[Wheel]:
        """A local candidate has already everything in local, no need to download."""
        kwargs = self._make_pip_wheel_args(ireq)
        with self.get_finder() as finder:
            with _allow_all_wheels():
                # temporarily allow all wheels to get a link.
                ireq.populate_link(finder, False, bool(hashes))
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
            if hashes:
                ireq.options["hashes"] = convert_hashes(hashes)
            shims.shim_unpack(
                link=ireq.link,
                download_dir=download_dir,
                location=ireq.source_dir,
                hashes=ireq.hashes(False),
                session=finder.session,
            )

            if ireq.link.is_wheel:
                return Wheel((context.cache("wheels") / ireq.link.filename).as_posix())
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
                wheel_cache = context.make_wheel_cache()
                builder = shims.WheelBuilder(preparer=preparer, wheel_cache=wheel_cache)
                output_dir = create_tracked_tempdir(prefix="pdm-ephem")
                wheel_path = builder._build_one(ireq, output_dir)
                if not wheel_path or not os.path.exists(wheel_path):
                    raise WheelBuildError(str(ireq))
                return Wheel(wheel_path)

    def get_working_set(self) -> pkg_resources.WorkingSet:
        """Get the working set based on local packages directory."""
        paths = self.get_paths()
        return pkg_resources.WorkingSet([paths["platlib"]])

    def marker_environment(self) -> Dict[str, Any]:
        """Get environment for marker evaluation"""
        return get_pep508_environment(self.python_executable)
