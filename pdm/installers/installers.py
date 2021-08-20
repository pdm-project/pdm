from __future__ import annotations

import io
import json
import os
import stat
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, cast

from installer import __version__
from installer._core import _determine_scheme, _process_WHEEL_file
from installer.destinations import SchemeDictionaryDestination
from installer.exceptions import InvalidWheelSource
from installer.records import RecordEntry
from installer.sources import WheelFile as _WheelFile
from installer.utils import parse_entrypoints

from pdm.installers.packages import CachedPackage
from pdm.models.environment import Environment
from pdm.termui import logger
from pdm.utils import cached_property

if TYPE_CHECKING:
    from typing import BinaryIO

    from installer.destinations import Scheme


class WheelFile(_WheelFile):
    @cached_property
    def dist_info_dir(self) -> str:
        namelist = self._zipfile.namelist()
        try:
            return next(
                name.split("/")[0]
                for name in namelist
                if name.split("/")[0].endswith(".dist-info")
            )
        except StopIteration:  # pragma: no cover
            canonical_name = super().dist_info_dir
            raise InvalidWheelSource(
                f"The wheel doesn't contain metadata {canonical_name!r}"
            )


class InstallDestination(SchemeDictionaryDestination):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.root_scheme = cast("Scheme", "purelib")

    def write_to_fs(
        self, scheme: Scheme, path: str | Path, stream: BinaryIO
    ) -> RecordEntry:
        target_path = os.path.join(self.scheme_dict[scheme], path)
        if os.path.exists(target_path):
            os.unlink(target_path)
        record_path = os.path.relpath(
            target_path, self.scheme_dict[self.root_scheme]
        ).replace("\\", "/")
        record = super().write_to_fs(scheme, path, stream)
        record.path = record_path
        return record


def install_wheel(
    wheel: str, environment: Environment, direct_url: dict[str, Any] | None = None
) -> None:
    """Install a normal wheel file into the environment."""
    additional_metadata = None
    if direct_url is not None:
        additional_metadata = {
            "direct_url.json": json.dumps(direct_url, indent=2).encode()
        }
    _install_wheel(
        wheel=wheel,
        interpreter=environment.interpreter.executable,
        script_kind=_get_kind(environment),
        scheme_dict=environment.get_paths(),
        additional_metadata=additional_metadata,
    )


def install_wheel_with_cache(
    wheel: str, environment: Environment, direct_url: dict[str, Any] | None = None
) -> None:
    """Only create .pth files referring to the cached package.
    If the cache doesn't exist, create one.
    """
    wheel_stem = Path(wheel).stem
    cache_path = environment.project.cache("packages") / wheel_stem
    package_cache = CachedPackage(cache_path)
    interpreter = environment.interpreter.executable
    script_kind = _get_kind(environment)
    if not cache_path.is_dir():
        logger.debug("Installing wheel into cached location %s", cache_path)
        cache_path.mkdir(exist_ok=True)
        _install_wheel(
            wheel=wheel,
            interpreter=interpreter,
            script_kind=script_kind,
            scheme_dict=package_cache.scheme(),
        )

    additional_metadata = {"REFER_TO": package_cache.path.as_posix().encode()}

    if direct_url is not None:
        additional_metadata["direct_url.json"] = json.dumps(
            direct_url, indent=2
        ).encode()

    def skip_files(scheme: Scheme, path: str) -> bool:
        return not (
            scheme == "scripts"
            or path.split("/")[0].endswith(".dist-info")
            or path.endswith(".pth")
        )

    filename = wheel_stem.split("-")[0] + ".pth"
    lib_path = package_cache.scheme()["purelib"]

    dist_info_dir = _install_wheel(
        wheel=wheel,
        interpreter=interpreter,
        script_kind=script_kind,
        scheme_dict=environment.get_paths(),
        excludes=skip_files,
        additional_files=[(None, filename, io.BytesIO(f"{lib_path}\n".encode()))],
        additional_metadata=additional_metadata,
    )
    package_cache.add_referrer(dist_info_dir)


def _install_wheel(
    wheel: str,
    interpreter: str,
    script_kind: str,
    scheme_dict: dict[str, str],
    excludes: Callable[[Scheme, str], bool] | None = None,
    additional_files: list[tuple[Scheme | None, str, BinaryIO]] | None = None,
    additional_metadata: dict[str, bytes] | None = None,
) -> str:
    """A lower level installation method that is copied from installer
    but is controlled by extra parameters.

    Return the .dist-info path
    """
    destination = InstallDestination(
        scheme_dict,
        interpreter=interpreter,
        script_kind=script_kind,
    )

    with WheelFile.open(wheel) as source:
        root_scheme = _process_WHEEL_file(source)
        destination.root_scheme = root_scheme

        # RECORD handling
        record_file_path = os.path.join(source.dist_info_dir, "RECORD")
        written_records = []

        # console-scripts and gui-scripts are copied anyway.
        if "entry_points.txt" in source.dist_info_filenames:
            entrypoints_text = source.read_dist_info("entry_points.txt")
            for name, module, attr, section in parse_entrypoints(entrypoints_text):
                record = destination.write_script(
                    name=name,
                    module=module,
                    attr=attr,
                    section=section,
                )
                written_records.append(record)

        for record_elements, stream in source.get_contents():
            source_record = RecordEntry.from_elements(*record_elements)
            path = source_record.path
            if os.path.normcase(path) == os.path.normcase(record_file_path):
                continue
            # Figure out where to write this file.
            scheme, destination_path = _determine_scheme(
                path=path,
                source=source,
                root_scheme=root_scheme,
            )
            if excludes is not None and excludes(scheme, path):
                continue
            record = destination.write_file(
                scheme=scheme,
                path=destination_path,
                stream=stream,
            )
            # add executable bit if necessary
            target_path = os.path.join(scheme_dict[scheme], destination_path)
            file_mode = stat.S_IMODE(source._zipfile.getinfo(path).external_attr >> 16)
            if file_mode & 0o111:
                new_mode = os.stat(target_path).st_mode
                new_mode |= (new_mode & 0o444) >> 2
                os.chmod(target_path, new_mode)
            written_records.append(record)

        # Write additional files
        if additional_files:
            for scheme, path, stream in additional_files:
                record = destination.write_file(
                    scheme=scheme or root_scheme,
                    path=path,
                    stream=stream,
                )
            written_records.append(record)

        # Write all the installation-specific metadata
        metadata = {
            "INSTALLER": f"installer {__version__}".encode(),
        }
        if additional_metadata:
            metadata.update(additional_metadata)
        for filename, contents in metadata.items():
            path = os.path.join(source.dist_info_dir, filename)

            with io.BytesIO(contents) as other_stream:
                record = destination.write_file(
                    scheme=root_scheme,
                    path=path,
                    stream=other_stream,
                )
            written_records.append(record)

        written_records.append(RecordEntry(record_file_path, None, None))
        destination.finalize_installation(
            scheme=root_scheme,
            record_file_path=record_file_path,
            records=written_records,
        )
        return os.path.join(scheme_dict[root_scheme], source.dist_info_dir)


def _get_kind(environment: Environment) -> str:
    if os.name != "nt":
        return "posix"
    is_32bit = environment.interpreter.is_32bit
    # TODO: support win arm64
    if is_32bit:
        return "win-ia32"
    else:
        return "win-amd64"
