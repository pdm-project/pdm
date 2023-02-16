from __future__ import annotations

import io
import itertools
import json
import os
import zipfile
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

from installer._core import _determine_scheme, _process_WHEEL_file, install
from installer.destinations import SchemeDictionaryDestination
from installer.exceptions import InvalidWheelSource
from installer.records import RecordEntry
from installer.sources import WheelFile as _WheelFile

from pdm.compat import cached_property
from pdm.installers.packages import CachedPackage
from pdm.termui import logger
from pdm.utils import fs_supports_symlink

if TYPE_CHECKING:
    from typing import Any, BinaryIO, Callable, Iterable

    from installer.destinations import Scheme
    from installer.sources import WheelContentElement

    from pdm.models.environment import Environment


@lru_cache()
def _is_python_package(root: str | Path) -> bool:
    for child in Path(root).iterdir():
        if (
            child.is_file()
            and child.suffix in (".py", ".pyc", ".pyo", ".pyd")
            or child.is_dir()
            and _is_python_package(child)
        ):
            return True
    return False


@lru_cache()
def _is_namespace_package(root: str) -> bool:
    if not _is_python_package(root):
        return False
    if not os.path.exists(os.path.join(root, "__init__.py")):  # PEP 420 style
        return True
    int_py_lines = [
        line.strip()
        for line in Path(root, "__init__.py").open(encoding="utf-8")
        if line.strip() and not line.strip().startswith("#")
    ]
    namespace_identifiers = [
        # pkg_resources style
        "__import__('pkg_resources').declare_namespace(__name__)",
        # pkgutil style
        "__path__ = __import__('pkgutil').extend_path(__path__, __name__)",
    ]
    checker = namespace_identifiers[:]
    checker.extend(item.replace("'", '"') for item in namespace_identifiers)
    return any(line in checker for line in int_py_lines)


def _create_symlinks_recursively(source: str, destination: str) -> Iterable[str]:
    """Create symlinks recursively from source to destination.
    Caveats: This don't work for pkgutil or pkg_resources namespace packages.
    package  <-- link
        __init__.py
    namespace_package  <-- mkdir
        foo.py  <-- link
        bar.py  <-- link
    """
    is_top = True
    for root, dirs, files in os.walk(source):
        bn = os.path.basename(root)
        if bn == "__pycache__" or bn.endswith(".dist-info"):
            dirs[:] = []
            continue
        relpath = os.path.relpath(root, source)
        destination_root = os.path.join(destination, relpath)
        if is_top:
            is_top = False
        elif not _is_namespace_package(root):
            # A package, create link for the parent dir and don't proceed
            # for child directories
            if os.path.exists(destination_root):
                os.remove(destination_root)
            os.symlink(root, destination_root, True)
            yield relpath
            dirs[:] = []
            continue
        # Otherwise, the directory is likely a namespace package,
        # mkdir and create links for all files inside.
        if not os.path.exists(destination_root):
            os.makedirs(destination_root)
        for f in files:
            if f.endswith(".pyc"):
                continue
            source_path = os.path.join(root, f)
            destination_path = os.path.join(destination_root, f)
            if os.path.exists(destination_path):
                os.remove(destination_path)
            os.symlink(source_path, destination_path, False)
            yield os.path.join(relpath, f)


class WheelFile(_WheelFile):
    def __init__(self, f: zipfile.ZipFile) -> None:
        super().__init__(f)
        self.exclude: Callable[[WheelFile, WheelContentElement], bool] | None = None
        self.additional_contents: Iterable[WheelContentElement] = []

    @cached_property
    def dist_info_dir(self) -> str:
        namelist = self._zipfile.namelist()
        try:
            return next(name.split("/")[0] for name in namelist if name.split("/")[0].endswith(".dist-info"))
        except StopIteration:  # pragma: no cover
            canonical_name = super().dist_info_dir
            raise InvalidWheelSource(f"The wheel doesn't contain metadata {canonical_name!r}") from None

    def get_contents(self) -> Iterator[WheelContentElement]:
        for element in super().get_contents():
            if self.exclude and self.exclude(self, element):
                continue
            yield element
        yield from self.additional_contents


class InstallDestination(SchemeDictionaryDestination):
    def __init__(self, *args: Any, symlink_to: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.symlink_to = symlink_to

    def write_to_fs(self, scheme: Scheme, path: str | Path, stream: BinaryIO, is_executable: bool) -> RecordEntry:
        target_path = os.path.join(self.scheme_dict[scheme], path)
        if os.path.exists(target_path):
            os.unlink(target_path)
        return super().write_to_fs(scheme, path, stream, is_executable)

    def finalize_installation(
        self,
        scheme: Scheme,
        record_file_path: str | Path,
        records: Iterable[tuple[Scheme, RecordEntry]],
    ) -> None:
        if self.symlink_to:
            # Create symlinks to the cached location
            for relpath in _create_symlinks_recursively(self.symlink_to, self.scheme_dict[scheme]):
                records = itertools.chain(
                    records,
                    [(scheme, RecordEntry(relpath.replace("\\", "/"), None, None))],
                )
        return super().finalize_installation(scheme, record_file_path, records)


def install_wheel(wheel: str, environment: Environment, direct_url: dict[str, Any] | None = None) -> None:
    """Install a normal wheel file into the environment."""
    additional_metadata = None
    if direct_url is not None:
        additional_metadata = {"direct_url.json": json.dumps(direct_url, indent=2).encode()}
    destination = InstallDestination(
        scheme_dict=environment.get_paths(),
        interpreter=str(environment.interpreter.executable),
        script_kind=_get_kind(environment),
    )
    _install_wheel(wheel=wheel, destination=destination, additional_metadata=additional_metadata)


def install_wheel_with_cache(wheel: str, environment: Environment, direct_url: dict[str, Any] | None = None) -> None:
    """Only create .pth files referring to the cached package.
    If the cache doesn't exist, create one.
    """
    wheel_stem = Path(wheel).stem
    cache_path = environment.project.cache("packages") / wheel_stem
    package_cache = CachedPackage(cache_path)
    interpreter = str(environment.interpreter.executable)
    script_kind = _get_kind(environment)
    use_symlink = environment.project.config["install.cache_method"] == "symlink" and fs_supports_symlink()
    if not cache_path.is_dir():
        logger.info("Installing wheel into cached location %s", cache_path)
        cache_path.mkdir(exist_ok=True)
        destination = InstallDestination(
            scheme_dict=package_cache.scheme(),
            interpreter=interpreter,
            script_kind=script_kind,
        )
        _install_wheel(wheel=wheel, destination=destination)

    additional_metadata = {"REFER_TO": package_cache.path.as_posix().encode()}

    if direct_url is not None:
        additional_metadata["direct_url.json"] = json.dumps(direct_url, indent=2).encode()

    def skip_files(source: WheelFile, element: WheelContentElement) -> bool:
        root_scheme = _process_WHEEL_file(source)
        scheme, path = _determine_scheme(element[0][0], source, root_scheme)
        return not (
            scheme not in ("purelib", "platlib")
            or path.split("/")[0].endswith(".dist-info")
            # We need to skip the *-nspkg.pth files generated by setuptools'
            # namespace_packages merchanism. See issue#623 for details
            or not use_symlink
            and path.endswith(".pth")
            and not path.endswith("-nspkg.pth")
        )

    additional_contents: list[WheelContentElement] = []
    lib_path = package_cache.scheme()["purelib"]
    if not use_symlink:
        # HACK: Prefix with aaa_ to make it processed as early as possible
        filename = "aaa_" + wheel_stem.split("-")[0] + ".pth"
        # use site.addsitedir() rather than a plain path to properly process .pth files
        stream = io.BytesIO(f"import site;site.addsitedir({lib_path!r})\n".encode())
        additional_contents.append(((filename, "", str(len(stream.getvalue()))), stream, False))

    destination = InstallDestination(
        scheme_dict=environment.get_paths(),
        interpreter=interpreter,
        script_kind=script_kind,
        symlink_to=lib_path if use_symlink else None,
    )

    dist_info_dir = _install_wheel(
        wheel=wheel,
        destination=destination,
        excludes=skip_files,
        additional_contents=additional_contents,
        additional_metadata=additional_metadata,
    )
    package_cache.add_referrer(dist_info_dir)


def _install_wheel(
    wheel: str,
    destination: InstallDestination,
    excludes: Callable[[WheelFile, WheelContentElement], bool] | None = None,
    additional_contents: Iterable[WheelContentElement] | None = None,
    additional_metadata: dict[str, bytes] | None = None,
) -> str:
    """A lower level installation method that is copied from installer
    but is controlled by extra parameters.

    Return the .dist-info path
    """
    with WheelFile.open(wheel) as source:
        root_scheme = _process_WHEEL_file(source)
        source.exclude = excludes
        if additional_contents:
            source.additional_contents = additional_contents
        install(source, destination, additional_metadata=additional_metadata or {})
    return os.path.join(destination.scheme_dict[root_scheme], source.dist_info_dir)


def _get_kind(environment: Environment) -> str:
    if os.name != "nt":
        return "posix"
    is_32bit = environment.interpreter.is_32bit
    # TODO: support win arm64
    if is_32bit:
        return "win-ia32"
    else:
        return "win-amd64"
