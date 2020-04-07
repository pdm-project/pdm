from __future__ import annotations

import collections
import os
import re
import shutil
import sys
import sysconfig
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional, Tuple

from distlib.scripts import ScriptMaker
from pip._internal.req import req_uninstall
from pip._internal.utils import misc
from pip._vendor import packaging, pkg_resources
from pip_shims import shims
from pythonfinder import Finder
from pythonfinder.environment import PYENV_INSTALLED, PYENV_ROOT

from pdm.exceptions import NoPythonVersion
from pdm.iostream import stream
from pdm.utils import (
    allow_all_wheels,
    cached_property,
    convert_hashes,
    create_tracked_tempdir,
    get_finder,
    get_pep508_environment,
    get_python_version,
    get_sys_config_paths,
    get_venv_python,
    temp_environ,
)

if TYPE_CHECKING:
    from pdm.project import Project
    from pdm._types import Source


class WorkingSet(collections.abc.Mapping):
    """A dict-like class that holds all installed packages in the lib directory."""

    def __init__(
        self,
        paths: Optional[List[str]] = None,
        python: Tuple[int, ...] = sys.version_info[:3],
    ):
        self.env = pkg_resources.Environment(paths, python=python)
        self.pkg_ws = pkg_resources.WorkingSet(paths)
        self.__add_editable_dists()

    def __getitem__(self, key: str) -> pkg_resources.Distribution:
        rv = self.env[key]
        if rv:
            return rv[0]
        else:
            raise KeyError(key)

    def __len__(self) -> int:
        return len(self.env._distmap)

    def __iter__(self) -> Iterator[str]:
        for item in self.env:
            yield item

    def __add_editable_dists(self):
        """Editable distributions are not present in pkg_resources.WorkingSet,
        Get them from self.env
        """
        missing_keys = [key for key in self if key not in self.pkg_ws.by_key]
        for key in missing_keys:
            self.pkg_ws.add(self[key])


class Environment:
    """Environment dependent stuff related to the selected Python interpreter."""

    is_global = False

    def __init__(self, project: Project) -> None:
        """
        :param project: the project instance
        """
        self.python_requires = project.python_requires
        self.project = project
        self._wheel_ensured = False

    @cached_property
    def python_executable(self) -> str:
        """Get the Python interpreter path."""
        config = self.project.config
        if config.get("python.path"):
            return config["python.path"]
        if PYENV_INSTALLED and config.get("python.use_pyenv", True):
            return os.path.join(PYENV_ROOT, "shims", "python")
        if "VIRTUAL_ENV" in os.environ:
            stream.echo(
                "An activated virtualenv is detected, reuse the interpreter now.",
                err=True,
                verbosity=stream.DETAIL,
            )
            return get_venv_python(self.project.root)

        # First try what `python` refers to.
        path = shutil.which("python")
        version = None
        if path:
            version = get_python_version(path, True)
        if not version or not self.python_requires.contains(version):
            finder = Finder()
            for python in finder.find_all_python_versions():
                version = get_python_version(python.path.as_posix(), True)
                if self.python_requires.contains(version):
                    path = python.path.as_posix()
                    break
            else:
                version = ".".join(map(str, sys.version_info[:3]))
                if self.python_requires.contains(version):
                    path = sys.executable
        if path:
            stream.echo(
                "Using Python interpreter: {} ({})".format(stream.green(path), version)
            )
            self.project.project_config["python.path"] = Path(path).as_posix()
            return path
        raise NoPythonVersion(
            "No Python that satisfies {} is found on the system.".format(
                self.python_requires
            )
        )

    def get_paths(self) -> Dict[str, str]:
        """Get paths like ``sysconfig.get_paths()`` for installation."""
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
        """Activate the environment. Manipulate the ``PYTHONPATH`` and patches ``pip``
        to be aware of local packages. This method acts like a context manager.
        """
        paths = self.get_paths()
        with temp_environ():
            old_paths = os.getenv("PYTHONPATH")
            if old_paths:
                new_paths = os.pathsep.join([paths["purelib"], old_paths])
            else:
                new_paths = paths["purelib"]
            os.environ["PYTHONPATH"] = new_paths
            python_root = os.path.dirname(self.python_executable)
            os.environ["PATH"] = os.pathsep.join(
                [python_root, paths["scripts"], os.environ["PATH"]]
            )
            working_set = self.get_working_set()
            _old_ws = pkg_resources.working_set
            pkg_resources.working_set = working_set.pkg_ws
            # HACK: Replace the is_local with environment version so that packages can
            # be removed correctly.
            _old_sitepackages = misc.site_packages
            misc.site_packages = paths["purelib"]
            _is_local = misc.is_local
            misc.is_local = req_uninstall.is_local = self.is_local
            _evaluate_marker = pkg_resources.evaluate_marker
            pkg_resources.evaluate_marker = self.evaluate_marker
            sys_executable = sys.executable
            sys.executable = self.python_executable
            yield
            sys.executable = sys_executable
            pkg_resources.evaluate_marker = _evaluate_marker
            misc.is_local = req_uninstall.is_local = _is_local
            misc.site_packages = _old_sitepackages
            pkg_resources.working_set = _old_ws

    def is_local(self, path) -> bool:
        """PEP 582 version of ``is_local()`` function."""
        return misc.normalize_path(path).startswith(
            misc.normalize_path(self.packages_path.as_posix())
        )

    def evaluate_marker(self, text: str, extra=None) -> bool:
        marker = packaging.markers.Marker(text)
        return marker.evaluate(self.marker_environment)

    @cached_property
    def packages_path(self) -> Path:
        """The local packages path."""
        pypackages = (
            self.project.root
            / "__pypackages__"
            / ".".join(map(str, get_python_version(self.python_executable)[:2]))
        )
        scripts = "Scripts" if os.name == "nt" else "bin"
        for subdir in [scripts, "include", "lib"]:
            pypackages.joinpath(subdir).mkdir(exist_ok=True, parents=True)
        return pypackages

    def _make_building_args(self, ireq: shims.InstallRequirement) -> Dict[str, Any]:
        src_dir = ireq.source_dir or self._get_source_dir()
        if ireq.editable:
            build_dir = src_dir
        else:
            build_dir = create_tracked_tempdir(prefix="pdm-build")
        download_dir = self.project.cache("pkgs")
        wheel_download_dir = self.project.cache("wheels")
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
        """Return the package finder of given index sources.

        :param sources: a list of sources the finder should search in.
        :param ignore_requires_python: whether to ignore the python version constraint.
        """
        sources = sources or []
        python_version = get_python_version(self.python_executable)[:2]
        finder = get_finder(
            sources,
            self.project.cache_dir.as_posix(),
            python_version,
            ignore_requires_python,
        )
        yield finder
        finder.session.close()

    def build(
        self,
        ireq: shims.InstallRequirement,
        hashes: Optional[Dict[str, str]] = None,
        allow_all: bool = True,
    ) -> str:
        """Build egg_info directory for editable candidates and a wheel for others.

        :param ireq: the InstallRequirment of the candidate.
        :param hashes: a dictionary of filename: hash_value to check against downloaded
        artifacts.
        :param allow_all: Allow building incompatible wheels.
        :returns: The full path of the built artifact.
        """
        from pip._internal.utils.temp_dir import global_tempdir_manager
        from pdm.builders import EditableBuilder
        from pdm.builders import WheelBuilder

        kwargs = self._make_building_args(ireq)
        with self.get_finder() as finder:
            if allow_all:
                with allow_all_wheels():
                    # temporarily allow all wheels to get a link.
                    ireq.populate_link(finder, False, bool(hashes))
            else:
                ireq.populate_link(finder, False, bool(hashes))
            if not ireq.editable and not ireq.req.name:
                ireq.source_dir = kwargs["build_dir"]
            else:
                ireq.ensure_has_source_dir(kwargs["build_dir"])

            download_dir = kwargs["download_dir"]
            only_download = False
            if ireq.link.is_wheel:
                download_dir = kwargs["wheel_download_dir"]
                only_download = True
            if hashes:
                ireq.options["hashes"] = convert_hashes(hashes)
            if not (ireq.editable and ireq.req.is_local_dir):
                with global_tempdir_manager():
                    downloaded = shims.shim_unpack(
                        link=ireq.link,
                        download_dir=download_dir,
                        location=ireq.source_dir,
                        hashes=ireq.hashes(False),
                        only_download=only_download,
                        session=finder.session,
                    )
                    # Preserve the downloaded file so that it won't be cleared.
                    if downloaded and only_download:
                        try:
                            shutil.copy(downloaded, download_dir)
                        except shutil.SameFileError:
                            pass
            # Now all source is prepared, build it.
            if ireq.link.is_wheel:
                return (self.project.cache("wheels") / ireq.link.filename).as_posix()
            if ireq.editable:
                builder_class = EditableBuilder
            else:
                builder_class = WheelBuilder
                self.ensure_wheel_package()
            kwargs["finder"] = finder
            with builder_class(ireq) as builder, self.activate():
                return builder.build(**kwargs)

    def get_working_set(self) -> WorkingSet:
        """Get the working set based on local packages directory."""
        paths = self.get_paths()
        return WorkingSet(
            [paths["platlib"]], python=get_python_version(self.python_executable)
        )

    @cached_property
    def marker_environment(self) -> Dict[str, Any]:
        """Get environment for marker evaluation"""
        return get_pep508_environment(self.python_executable)

    def which(self, command: str) -> str:
        """Get the full path of the given executable against this environment."""
        if not os.path.isabs(command) and command.startswith("python"):
            python = os.path.splitext(command)[0]
            version = python[6:]
            this_version = get_python_version(self.python_executable, True)
            if not version or this_version.startswith(version):
                return self.python_executable
        # Fallback to use shutil.which to find the executable
        return shutil.which(command, path=os.getenv("PATH"))

    def ensure_wheel_package(self) -> None:
        """Ensure wheel package is available and install if it isn't."""
        from pdm.installers import Installer
        from pdm.models.requirements import parse_requirement
        from pdm.models.candidates import Candidate

        if self._wheel_ensured or "wheel" in self.get_working_set():
            return
        req = parse_requirement("wheel")
        candidate = Candidate(req, self, "wheel")
        Installer(self).install(candidate)
        self._wheel_ensured = True

    def update_shebangs(self, new_path: str) -> None:
        """Update the shebang lines"""
        scripts = self.get_paths()["scripts"]
        maker = ScriptMaker(None, None)
        maker.executable = new_path
        shebang = maker._get_shebang("utf-8").rstrip()
        for child in Path(scripts).iterdir():
            if not child.is_file() or child.suffix not in (".exe", ".py"):
                continue
            child.write_bytes(
                re.sub(rb"#!.+?python.*?$", shebang, child.read_bytes(), flags=re.M)
            )


class GlobalEnvironment(Environment):
    """Global environment"""

    is_global = True

    def get_paths(self) -> Dict[str, str]:
        paths = get_sys_config_paths(self.python_executable)
        paths["prefix"] = paths["data"]
        paths["headers"] = paths["include"]
        return paths

    def is_local(self, path) -> bool:
        return misc.normalize_path(path).startswith(
            misc.normalize_path(self.get_paths()["prefix"])
        )

    @property
    def packages_path(self) -> Optional[Path]:
        return None
