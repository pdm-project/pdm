from __future__ import annotations

import json
import os
import stat
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

from installer import install as _install
from installer._core import _process_WHEEL_file
from installer.destinations import SchemeDictionaryDestination, WheelDestination
from installer.exceptions import InvalidWheelSource
from installer.records import RecordEntry
from installer.sources import WheelContentElement, WheelSource
from installer.sources import WheelFile as _WheelFile

from pdm.models.cached_package import CachedPackage

if TYPE_CHECKING:
    from typing import Any, BinaryIO, Iterable, Literal

    from installer.destinations import Scheme
    from installer.sources import WheelContentElement

    from pdm.environments import BaseEnvironment

    LinkMethod = Literal["symlink", "hardlink", "copy"]


def _get_dist_name(wheel_path: str) -> str:
    from packaging.utils import parse_wheel_filename

    return parse_wheel_filename(os.path.basename(wheel_path))[0]


class WheelFile(_WheelFile):
    @cached_property
    def dist_info_dir(self) -> str:
        namelist = self._zipfile.namelist()
        try:
            return next(name.split("/")[0] for name in namelist if name.split("/")[0].endswith(".dist-info"))
        except StopIteration:  # pragma: no cover
            canonical_name = super().dist_info_dir
            raise InvalidWheelSource(f"The wheel doesn't contain metadata {canonical_name!r}") from None


class PackageWheelSource(WheelSource):
    def __init__(self, package: CachedPackage) -> None:
        self.package = package

        distribution, version = package.path.name.split("-")[:2]
        super().__init__(distribution, version)

    @cached_property
    def dist_info_dir(self) -> str:
        return self.package.dist_info.name

    @property
    def dist_info_filenames(self) -> list[str]:
        return os.listdir(self.package.dist_info)

    def read_dist_info(self, filename: str) -> str:
        return self.package.dist_info.joinpath(filename).read_text("utf-8")

    def iter_files(self) -> Iterable[Path]:
        for root, _, files in os.walk(self.package.path):
            for file in files:
                if Path(root) == self.package.path and file in CachedPackage.cache_files:
                    continue
                yield Path(root, file)

    def get_contents(self) -> Iterator[WheelContentElement]:
        from installer.records import parse_record_file

        record_lines = self.read_dist_info("RECORD").splitlines()
        records = parse_record_file(record_lines)
        record_mapping = {record[0]: record for record in records}

        for item in self.iter_files():
            fn = item.relative_to(self.package.path).as_posix()

            # Pop record with empty default, because validation is handled by `validate_record`
            record = record_mapping.pop(fn, (fn, "", ""))

            # Borrowed from:
            # https://github.com/pypa/pip/blob/0f21fb92/src/pip/_internal/utils/unpacking.py#L96-L100
            mode = item.stat().st_mode
            is_executable = bool(mode and stat.S_ISREG(mode) and mode & 0o111)

            with item.open("rb") as stream:
                yield record, stream, is_executable


class InstallDestination(SchemeDictionaryDestination):
    def __init__(
        self,
        *args: Any,
        link_method: LinkMethod = "copy",
        rename_pth: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.link_method = link_method
        self.rename_pth = rename_pth

    def write_to_fs(self, scheme: Scheme, path: str, stream: BinaryIO, is_executable: bool) -> RecordEntry:
        from installer.records import Hash
        from installer.utils import copyfileobj_with_hashing, make_file_executable

        target_path = os.path.join(self.scheme_dict[scheme], path)
        if os.path.exists(target_path):
            os.unlink(target_path)

        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        if self.rename_pth and target_path.endswith(".pth") and "/" not in path:
            # Postpone the creation of pth files since it may cause race condition
            # when multiple packages are installed at the same time.
            target_path += ".pdmtmp"
        if self.link_method == "copy" or not hasattr(stream, "name"):
            with open(target_path, "wb") as f:
                hash_, size = copyfileobj_with_hashing(stream, f, self.hash_algorithm)
        else:
            src_path = stream.name
            # create links, we don't need the stream anymore
            stream.close()
            if self.link_method == "symlink":
                os.symlink(src_path, target_path)
            else:  # hardlink
                os.link(src_path, target_path)
            hash_ = ""
            size = os.path.getsize(target_path)

        if is_executable:
            make_file_executable(target_path)
        return RecordEntry(path, Hash(self.hash_algorithm, hash_), size)


def _get_link_method(cache_method: str) -> LinkMethod:
    from pdm import utils

    if "symlink" in cache_method and utils.fs_supports_link_method("symlink"):
        return "symlink"

    if "link" in cache_method and utils.fs_supports_link_method("link"):
        return "hardlink"
    return "copy"


def install_wheel(
    wheel: Path,
    environment: BaseEnvironment,
    direct_url: dict[str, Any] | None = None,
    install_links: bool = False,
    rename_pth: bool = False,
) -> str:
    """Only create .pth files referring to the cached package.
    If the cache doesn't exist, create one.
    """
    interpreter = str(environment.interpreter.executable)
    script_kind = environment.script_kind
    # the cache_method can be any of "symlink", "hardlink", "copy" and "pth"
    cache_method: str = environment.project.config["install.cache_method"]
    dist_name = wheel.name.split("-")[0]
    link_method: LinkMethod | None
    if not install_links or dist_name == "editables":
        link_method = "copy"
    else:
        link_method = _get_link_method(cache_method)

    additional_metadata: dict[str, bytes] = {}
    if direct_url is not None:
        additional_metadata["direct_url.json"] = json.dumps(direct_url, indent=2).encode()

    destination = InstallDestination(
        scheme_dict=environment.get_paths(dist_name),
        interpreter=interpreter,
        script_kind=script_kind,
        link_method=link_method,
        rename_pth=rename_pth,
    )
    if install_links:
        package = environment.project.package_cache.cache_wheel(wheel)
        source = PackageWheelSource(package)
        if link_method == "symlink":
            # Track usage when symlink is used
            additional_metadata["REFER_TO"] = package.path.as_posix().encode()
        dist_info_dir = install(source, destination=destination, additional_metadata=additional_metadata)
        if link_method == "symlink":
            package.add_referrer(dist_info_dir)
    else:
        with WheelFile.open(wheel) as source:
            dist_info_dir = install(source, destination=destination, additional_metadata=additional_metadata)
    return dist_info_dir


def install(
    source: WheelSource, destination: WheelDestination, additional_metadata: dict[str, bytes] | None = None
) -> str:
    """A lower level installation method that is copied from installer
    but is controlled by extra parameters.

    Return the .dist-info path
    """
    _install(source, destination, additional_metadata=additional_metadata or {})
    root_scheme = _process_WHEEL_file(source)
    return os.path.join(destination.scheme_dict[root_scheme], source.dist_info_dir)
