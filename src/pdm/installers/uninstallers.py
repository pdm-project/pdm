from __future__ import annotations

import abc
import glob
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Iterable, TypeVar, cast

from pdm import termui
from pdm.exceptions import UninstallError
from pdm.installers.packages import CachedPackage
from pdm.utils import is_egg_link, is_path_relative_to

if TYPE_CHECKING:
    from pdm.compat import Distribution
    from pdm.models.environment import Environment

_T = TypeVar("_T", bound="BaseRemovePaths")


def renames(old: str, new: str) -> None:
    """Like os.renames(), but handles renaming across devices."""
    # Implementation borrowed from os.renames().
    head, tail = os.path.split(new)
    if head and tail and not os.path.exists(head):
        os.makedirs(head)

    shutil.move(old, new)

    head, tail = os.path.split(old)
    if head and tail:
        try:
            os.removedirs(head)
        except OSError:
            pass


def compress_for_rename(paths: Iterable[str]) -> set[str]:
    """Returns a set containing the paths that need to be renamed.

    This set may include directories when the original sequence of paths
    included every file on disk.
    """
    case_map = {os.path.normcase(p): p for p in paths if os.path.exists(p)}
    remaining = set(case_map)
    unchecked = sorted({os.path.split(p)[0] for p in case_map.values()}, key=len)
    wildcards: set[str] = set()

    def norm_join(*a: str) -> str:
        return os.path.normcase(os.path.join(*a))

    for root in unchecked:
        if any(os.path.normcase(root).startswith(w) for w in wildcards):
            # This directory has already been handled.
            continue

        all_files: set[str] = set()
        for dirname, subdirs, files in os.walk(root):
            all_files.update(norm_join(root, dirname, f) for f in files)
            for d in subdirs:
                norm_path = norm_join(root, dirname, d)
                if os.path.islink(norm_path):
                    all_files.add(norm_path)

        # If all the files we found are in our remaining set of files to
        # remove, then remove them from the latter set and add a wildcard
        # for the directory.
        if not (all_files - remaining):
            remaining.difference_update(all_files)
            wildcards.add(root + os.sep)

    collected = set(map(case_map.__getitem__, remaining)) | wildcards
    shortened: set[str] = set()
    # Filter out any paths that are sub paths of another path in the path collection.
    for path in sorted(collected, key=len):
        if not any(is_path_relative_to(path, p) for p in shortened):
            shortened.add(path)
    return shortened


def _script_names(script_name: str, is_gui: bool) -> Iterable[str]:
    yield script_name
    if os.name == "nt":
        yield script_name + ".exe"
        yield script_name + ".exe.manifest"
        if is_gui:
            yield script_name + "-script.pyw"
        else:
            yield script_name + "-script.py"


def _cache_file_from_source(py_file: str) -> Iterable[str]:
    py2_cache = py_file[:-3] + ".pyc"
    if os.path.isfile(py2_cache):
        yield py2_cache
    parent, base = os.path.split(py_file)
    cache_dir = os.path.join(parent, "__pycache__")
    yield from glob.glob(os.path.join(cache_dir, base[:-3] + ".*.pyc"))


def _get_file_root(path: str, base: str) -> str | None:
    try:
        rel_path = Path(path).relative_to(base)
    except ValueError:
        return None
    else:
        root = rel_path.parts[0] if len(rel_path.parts) > 1 else ""
        return os.path.normcase(os.path.join(base, root))


class BaseRemovePaths(abc.ABC):
    """A collection of paths and/or pth entries to remove"""

    def __init__(self, dist: Distribution, environment: Environment) -> None:
        self.dist = dist
        self.environment = environment
        self._paths: set[str] = set()
        self._pth_entries: set[str] = set()
        self.refer_to: str | None = None

    @abc.abstractmethod
    def remove(self) -> None:
        """Remove the files"""

    @abc.abstractmethod
    def commit(self) -> None:
        """Commit the removal"""

    @abc.abstractmethod
    def rollback(self) -> None:
        """Roll back the removal operations"""

    @classmethod
    def from_dist(cls: type[_T], dist: Distribution, environment: Environment) -> _T:
        """Create an instance from the distribution"""
        scheme = environment.get_paths()
        instance = cls(dist, environment)
        meta_location = os.path.normcase(dist._path.absolute())  # type: ignore[attr-defined]
        dist_location = os.path.dirname(meta_location)
        if is_egg_link(dist):  # pragma: no cover
            egg_link_path = cast("Path | None", getattr(dist, "link_file", None))
            if not egg_link_path:
                termui.logger.warn(
                    "No egg link is found for editable distribution %s, do nothing.",
                    dist.metadata["Name"],
                )
            else:
                link_pointer = os.path.normcase(egg_link_path.open("rb").readline().decode().strip())
                if link_pointer != dist_location:
                    raise UninstallError(
                        f"The link pointer in {egg_link_path} doesn't match "
                        f"the location of {dist.metadata['Name']}(at {dist_location}"
                    )
                instance.add_path(str(egg_link_path))
                instance.add_pth(link_pointer)
        elif dist.files:
            for file in dist.files:
                location = dist.locate_file(file)
                instance.add_path(str(location))
                bare_name, ext = os.path.splitext(location)
                if ext == ".py":
                    # .pyc files are added by add_path()
                    instance.add_path(bare_name + ".pyo")

        bin_dir = scheme["scripts"]

        if os.path.isdir(os.path.join(meta_location, "scripts")):  # pragma: no cover
            for script in os.listdir(os.path.join(meta_location, "scripts")):
                instance.add_path(os.path.join(bin_dir, script))
                if os.name == "nt":
                    instance.add_path(os.path.join(bin_dir, script) + ".bat")

        # find console_scripts
        _scripts_to_remove: list[str] = []
        for ep in dist.entry_points:
            if ep.group == "console_scripts":
                _scripts_to_remove.extend(_script_names(ep.name, False))
            elif ep.group == "gui_scripts":
                _scripts_to_remove.extend(_script_names(ep.name, True))

        for s in _scripts_to_remove:
            instance.add_path(os.path.join(bin_dir, s))
        return instance

    def add_pth(self, line: str) -> None:
        self._pth_entries.add(line)

    def add_path(self, path: str) -> None:
        normalized_path = os.path.normcase(os.path.expanduser(os.path.abspath(path)))
        self._paths.add(normalized_path)
        if path.endswith(".py"):
            self._paths.update(_cache_file_from_source(normalized_path))
        elif path.replace("\\", "/").endswith(".dist-info/REFER_TO"):
            line = open(path, "rb").readline().decode().strip()
            if line:
                self.refer_to = line


class StashedRemovePaths(BaseRemovePaths):
    """Stash the paths to temporarily location and remove them after commit"""

    PTH_REGISTRY = "easy-install.pth"

    def __init__(self, dist: Distribution, environment: Environment) -> None:
        super().__init__(dist, environment)
        self._pth_file = os.path.join(self.environment.get_paths()["purelib"], self.PTH_REGISTRY)
        self._saved_pth: bytes | None = None
        self._stashed: list[tuple[str, str]] = []
        self._tempdirs: dict[str, TemporaryDirectory] = {}

    def remove(self) -> None:
        self._remove_pth()
        self._stash_files()

    def _remove_pth(self) -> None:
        if not self._pth_entries:
            return
        self._saved_pth = open(self._pth_file, "rb").read()
        endline = "\r\n" if b"\r\n" in self._saved_pth else "\n"
        lines = self._saved_pth.decode().splitlines()
        for item in self._pth_entries:
            termui.logger.debug("Removing pth entry: %s", item)
            lines.remove(item)
        with open(self._pth_file, "wb") as f:
            f.write((endline.join(lines) + endline).encode("utf8"))

    def _stash_files(self) -> None:
        paths_to_rename = sorted(compress_for_rename(self._paths))
        prefix = os.path.abspath(self.environment.get_paths()["prefix"])

        for old_path in paths_to_rename:
            if not os.path.exists(old_path):
                continue
            is_dir = os.path.isdir(old_path) and not os.path.islink(old_path)
            termui.logger.debug("Removing %s %s", "directory" if is_dir else "file", old_path)
            if old_path.endswith(".pyc"):
                # Don't stash cache files, remove them directly
                os.unlink(old_path)
                continue
            root = _get_file_root(old_path, prefix)
            if root is None:
                termui.logger.debug("File path %s is not under packages root %s, skip", old_path, prefix)
                continue
            if root not in self._tempdirs:
                self._tempdirs[root] = TemporaryDirectory("-uninstall", "pdm-")
            new_root = self._tempdirs[root].name
            relpath = os.path.relpath(old_path, root)
            new_path = os.path.join(new_root, relpath)
            if is_dir and os.path.isdir(new_path):
                os.rmdir(new_path)
            renames(old_path, new_path)
            self._stashed.append((old_path, new_path))

    def commit(self) -> None:
        for tempdir in self._tempdirs.values():
            try:
                tempdir.cleanup()
            except FileNotFoundError:
                pass
        self._tempdirs.clear()
        self._stashed.clear()
        self._saved_pth = None
        if self.refer_to:
            termui.logger.info("Unlink from cached package %s", self.refer_to)
            CachedPackage(self.refer_to).remove_referrer(os.path.dirname(self.refer_to))
            self.refer_to = None

    def rollback(self) -> None:
        if not self._stashed:
            termui.logger.error("Can't rollback, not uninstalled yet")
            return
        if self._saved_pth is not None:
            with open(self._pth_file, "wb") as f:
                f.write(self._saved_pth)
        for old_path, new_path in self._stashed:
            termui.logger.debug("Rollback %s\n from %s", old_path, new_path)
            if os.path.isfile(old_path) or os.path.islink(old_path):
                os.unlink(old_path)
            elif os.path.isdir(old_path):
                shutil.rmtree(old_path)
            renames(new_path, old_path)
        self.commit()
