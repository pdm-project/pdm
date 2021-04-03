from __future__ import annotations

import collections
import os
import re
import shutil
import sys
import sysconfig
from contextlib import contextmanager
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Generator, Iterator, List, Optional, Tuple

from distlib.scripts import ScriptMaker
from pip._vendor import packaging, pkg_resources

from pdm import termui
from pdm.models import pip_shims
from pdm.models.auth import make_basic_auth
from pdm.models.builders import EnvBuilder
from pdm.models.in_process import (
    get_pep508_environment,
    get_python_version,
    get_sys_config_paths,
)
from pdm.models.pip_shims import misc, req_uninstall
from pdm.utils import (
    allow_all_wheels,
    cached_property,
    convert_hashes,
    create_tracked_tempdir,
    expand_env_vars_in_auth,
    get_finder,
    get_python_version_string,
    populate_link,
    temp_environ,
)

if TYPE_CHECKING:
    from pdm._types import Source
    from pdm.project import Project

_egg_info_re = re.compile(r"([a-z0-9_.]+)-([a-z0-9_.!+-]+)", re.IGNORECASE)


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
        yield from self.env

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
        self.python_executable = project.python_executable
        self._essential_installed = False
        self.auth = make_basic_auth(
            self.project.sources, self.project.core.ui.verbosity >= termui.DETAIL
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
    def activate(self) -> Iterator:
        """Activate the environment. Manipulate the ``PYTHONPATH`` and patches ``pip``
        to be aware of local packages. This method acts like a context manager.

        :param site_packages: whether to inject base site-packages into the sub env.
        """
        paths = self.get_paths()
        with temp_environ():
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
            bin_py = req_uninstall.bin_py
            req_uninstall.bin_py = paths["scripts"]
            sys._original_executable = sys.executable
            sys.executable = self.python_executable
            yield
            sys.executable = sys._original_executable
            del sys._original_executable
            pkg_resources.evaluate_marker = _evaluate_marker
            misc.is_local = req_uninstall.is_local = _is_local
            req_uninstall.bin_py = bin_py
            misc.site_packages = _old_sitepackages
            pkg_resources.working_set = _old_ws

    def is_local(self, path: PathLike) -> bool:
        """PEP 582 version of ``is_local()`` function."""
        return misc.normalize_path(path).startswith(
            misc.normalize_path(self.packages_path.as_posix())
        )

    def evaluate_marker(self, text: str, extra: Any = None) -> bool:
        marker = packaging.markers.Marker(text)
        return marker.evaluate(self.marker_environment)

    @cached_property
    def packages_path(self) -> Path:
        """The local packages path."""
        version, is_64bit = get_python_version(self.python_executable, True, 2)
        pypackages = (
            self.project.root
            / "__pypackages__"
            / get_python_version_string(version, is_64bit)
        )
        if not pypackages.exists() and not is_64bit:
            compatible_packages = pypackages.parent / get_python_version_string(
                version, True
            )
            if compatible_packages.exists():
                pypackages = compatible_packages
        scripts = "Scripts" if os.name == "nt" else "bin"
        for subdir in [scripts, "include", "lib"]:
            pypackages.joinpath(subdir).mkdir(exist_ok=True, parents=True)
        return pypackages

    def _get_build_dir(self, ireq: pip_shims.InstallRequirement) -> str:
        if ireq.editable:
            return ireq.source_dir or self._get_source_dir()
        else:
            return create_tracked_tempdir(prefix="pdm-build-")

    def _get_source_dir(self) -> str:
        packages_dir = self.packages_path
        if packages_dir:
            src_dir = packages_dir / "src"
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
    ) -> Generator[pip_shims.PackageFinder, None, None]:
        """Return the package finder of given index sources.

        :param sources: a list of sources the finder should search in.
        :param ignore_requires_python: whether to ignore the python version constraint.
        """
        if sources is None:
            sources = self.project.sources
        for source in sources:
            source["url"] = expand_env_vars_in_auth(source["url"])

        python_version, _ = get_python_version(self.python_executable, digits=2)
        finder = get_finder(
            sources,
            self.project.cache_dir.as_posix(),
            python_version,
            ignore_requires_python,
        )
        # Reuse the auth across sessions to avoid prompting repeatly.
        finder.session.auth = self.auth
        yield finder
        finder.session.close()

    def build(
        self,
        ireq: pip_shims.InstallRequirement,
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
        build_dir = self._get_build_dir(ireq)
        wheel_cache = self.project.make_wheel_cache()
        supported_tags = pip_shims.get_supported(
            "".join(map(str, get_python_version(self.python_executable, digits=2)[0]))
        )
        with self.get_finder(ignore_requires_python=True) as finder:
            with allow_all_wheels(allow_all):
                # temporarily allow all wheels to get a link.
                populate_link(finder, ireq, False)
            ireq.link = pip_shims.Link(
                expand_env_vars_in_auth(
                    ireq.link.url.replace(
                        "${PROJECT_ROOT}", self.project.root.as_posix().lstrip("/")
                    )
                )
            )
            if hashes is None and not ireq.editable:
                # If hashes are not given and cache is hit, replace the link with the
                # cached one. This can speed up by skipping the download and build.
                cache_entry = wheel_cache.get_cache_entry(
                    ireq.link,
                    ireq.req.project_name,
                    supported_tags,
                )
                if cache_entry is not None:
                    termui.logger.debug("Using cached wheel link: %s", cache_entry.link)
                    ireq.link = cache_entry.link
            if not ireq.editable and not ireq.req.name:
                ireq.source_dir = build_dir
            else:
                ireq.ensure_has_source_dir(build_dir)

            if hashes:
                ireq.hash_options = convert_hashes(hashes)
            if not (ireq.editable and ireq.req.is_local_dir):
                downloader = pip_shims.Downloader(finder.session, "off")
                downloaded = pip_shims.unpack_url(
                    ireq.link,
                    ireq.source_dir,
                    downloader,
                    hashes=ireq.hashes(False),
                )

                if ireq.link.is_wheel:
                    # If the file is a wheel, return the downloaded file directly.
                    return downloaded.path

        # Check the built wheel cache again after hashes are resolved.
        if not ireq.editable:
            cache_entry = wheel_cache.get_cache_entry(
                ireq.link,
                ireq.req.project_name,
                supported_tags,
            )
            if cache_entry is not None:
                termui.logger.debug("Using cached wheel link: %s", cache_entry.link)
                return cache_entry.link.file_path

        # Otherwise, as all source is already prepared, build it.
        with EnvBuilder(ireq.unpacked_source_directory, self) as builder:
            if ireq.editable:
                ret = builder.build_egg_info(build_dir)
                ireq.metadata_directory = ret
                return ret
            should_cache = False
            if ireq.link.is_vcs:
                vcs = pip_shims.VcsSupport()
                vcs_backend = vcs.get_backend_for_scheme(ireq.link.scheme)
                if vcs_backend.is_immutable_rev_checkout(
                    ireq.link.url, ireq.source_dir
                ):
                    should_cache = True
            else:
                base, _ = ireq.link.splitext()
                if _egg_info_re.search(base) is not None:
                    # Determine whether the string looks like an egg_info.
                    should_cache = True
            output_dir = (
                wheel_cache.get_path_for_link(ireq.link) if should_cache else build_dir
            )
            if not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)
            return builder.build_wheel(output_dir)

    def get_working_set(self) -> WorkingSet:
        """Get the working set based on local packages directory."""
        paths = self.get_paths()
        return WorkingSet(
            [paths["platlib"], paths["purelib"]],
            python=get_python_version(self.python_executable)[0],
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
            this_version, _ = get_python_version(self.python_executable, True)
            if not version or this_version.startswith(version):
                return self.python_executable
        # Fallback to use shutil.which to find the executable
        this_path = self.get_paths()["scripts"]
        python_root = os.path.dirname(self.python_executable)
        new_path = os.pathsep.join([python_root, this_path, os.getenv("PATH", "")])
        return shutil.which(command, path=new_path)

    def update_shebangs(self, new_path: str) -> None:
        """Update the shebang lines"""
        scripts = self.get_paths()["scripts"]
        maker = ScriptMaker(None, None)
        maker.executable = new_path
        shebang = maker._get_shebang("utf-8").rstrip().replace(b"\\", b"\\\\")
        for child in Path(scripts).iterdir():
            if not child.is_file() or child.suffix not in (".exe", ".py", ""):
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

    def is_local(self, path: PathLike) -> bool:
        return misc.normalize_path(path).startswith(
            misc.normalize_path(self.get_paths()["prefix"])
        )

    @property
    def packages_path(self) -> Optional[Path]:
        return None
