import contextlib
import glob
import hashlib
import os
import shutil
import stat
import tempfile
import zipfile
from base64 import urlsafe_b64encode
from io import StringIO
from typing import List, Tuple

from pip_shims import shims
from pkg_resources import safe_name, safe_version, to_filename

from pdm.builders.base import Builder
from pdm.context import context
from pdm.exceptions import WheelBuildError
from pdm.utils import cached_property, get_abi_tag
from vistir.path import normalize_path

WHEEL_FILE_FORMAT = """\
Wheel-Version: 1.0
Generator: poetry {version}
Root-Is-Purelib: {pure_lib}
Tag: {tag}
"""


class WheelBuilder(Builder):
    def __init__(self, ireq: shims.InstallRequirement):
        self._records = []  # type: List[Tuple[str, str, str]]
        super().__init__(ireq)

    def build(self, build_dir: str, **kwargs) -> str:
        if not self.project.is_pdm:
            return self._build_other(build_dir, **kwargs)
        return self._build_pdm(build_dir, **kwargs)

    def _build_other(self, build_dir: str, **kwargs) -> str:
        finder = kwargs.pop("finder")
        if not self.ireq.req.name:
            # Name is not available for a tarball distribution. Get the package name
            # from package's egg info.
            # `prepare_metadata()` won't work if there is a `req` attribute.
            req = self.ireq.req
            self.ireq.req = None
            self.ireq.prepare_metadata()
            req.name = self.ireq.metadata["Name"]
            self.ireq.req = req

        with shims.make_preparer(
            finder=finder, session=finder.session, **kwargs
        ) as preparer:
            wheel_cache = context.make_wheel_cache()
            builder = shims.WheelBuilder(preparer=preparer, wheel_cache=wheel_cache)
            wheel_path = builder._build_one(self.ireq, build_dir)
            if not wheel_path or not os.path.exists(wheel_path):
                raise WheelBuildError(str(self.ireq))
            return wheel_path

    def _build_pdm(self, build_dir: str, **kwargs) -> str:
        if not os.path.exists(build_dir):
            os.makedirs(build_dir, exist_ok=True)

        context.io.echo("- Building {}...".format(context.io.cyan("wheel")))
        self._records.clear()
        fd, temp_path = tempfile.mkstemp(suffix=".whl")
        os.close(fd)

        with zipfile.ZipFile(
            temp_path, mode="w", compression=zipfile.ZIP_DEFLATED
        ) as zip_file:
            self._copy_module(zip_file)
            self._build(zip_file)
            self._write_metadata(zip_file)

        target = os.path.join(build_dir, self.wheel_filename)
        if os.path.exists(target):
            os.unlink(target)
        shutil.move(temp_path, target)

        context.io.echo("- Built {}".format(context.io.cyan(os.path.basename(target))))
        return target

    @property
    def wheel_filename(self) -> str:
        name = to_filename(self.meta.project_name)
        version = to_filename(safe_version(self.meta.version))
        return f"{name}-{version}-{self.tag}.whl"

    @cached_property
    def tag(self) -> str:
        if self.meta.build:
            info = self.project.environment.marker_environment()
            platform = to_filename(
                safe_name(info["platform_system"] + "-" + info["platform_machine"])
            )
            implementation = info["implementation_name"]
            impl_name = (
                "cp"
                if implementation.startswith("cp")
                else "jp"
                if implementation.startswith("jp")
                else "ip"
                if implementation.startswith("ir")
                else "pp"
                if implementation.startswith("pypy")
                else "unknown"
            )
            impl_ver = (
                info["python_full_version"].replace(".", "")
                if impl_name == "pp"
                else info["python_version"].replace(".", "")
            )
            impl = impl_name + impl_ver
            abi_tag = get_abi_tag(
                tuple(int(p) for p in info["python_version"].split("."))
            )
            tag = (impl, abi_tag, platform)
        else:
            platform = "any"
            if self.project.python_requires.supports_py2():
                impl = "py2.py3"
            else:
                impl = "py3"

            tag = (impl, "none", platform)

        return "-".join(tag)

    @property
    def dist_info_name(self) -> str:
        name = to_filename(self.meta.project_name)
        version = to_filename(safe_version(self.meta.version))
        return f"{name}-{version}.dist-info"

    def _write_record(self, fp):
        for row in self._records:
            row = normalize_path(row[0]), *row[1:]
            fp.write(",".join(row) + "\n")

    def _write_metadata(self, wheel):
        dist_info = self.dist_info_name
        if self.meta.entry_points:
            with self._write_to_zip(wheel, dist_info + "/entry_points.txt") as f:
                self._write_entry_points(f)

        with self._write_to_zip(wheel, dist_info + "/WHEEL") as f:
            self._write_wheel_file(f)

        with self._write_to_zip(wheel, dist_info + "/METADATA") as f:
            self._write_metadata_file(f)

        for pat in ("COPYING", "LICENSE"):
            for path in glob.glob(pat + "*"):
                if os.path.isfile(path):
                    self._add_file(wheel, path, f"{dist_info}/{path}")

        with self._write_to_zip(wheel, dist_info + "/RECORD") as f:
            self._records.append((dist_info + "/RECORD", "", ""))
            self._write_record(f)

    @contextlib.contextmanager
    def _write_to_zip(self, wheel, rel_path):
        sio = StringIO()
        yield sio

        # The default is a fixed timestamp rather than the current time, so
        # that building a wheel twice on the same computer can automatically
        # give you the exact same result.
        date_time = (2016, 1, 1, 0, 0, 0)
        zi = zipfile.ZipInfo(rel_path, date_time)
        b = sio.getvalue().encode("utf-8")
        hashsum = hashlib.sha256(b)
        hash_digest = urlsafe_b64encode(hashsum.digest()).decode("ascii").rstrip("=")

        wheel.writestr(zi, b, compress_type=zipfile.ZIP_DEFLATED)
        context.io.echo(f" - Adding: {rel_path}", verbosity=context.io.DETAIL)
        self._records.append((rel_path, hash_digest, str(len(b))))

    def _build(self, wheel):
        if not self.meta.build:
            return
        self.ensure_setup_py()
        # TODO: C extension build

    def _copy_module(self, wheel):
        for path in self.find_files_to_add():
            self._add_file(wheel, str(path))

    def _add_file(self, wheel, full_path, rel_path=None):
        if not rel_path:
            rel_path = full_path
        if os.sep != "/":
            # We always want to have /-separated paths in the zip file and in RECORD
            rel_path = rel_path.replace(os.sep, "/")
        context.io.echo(f" - Adding: {rel_path}", verbosity=context.io.DETAIL)
        zinfo = zipfile.ZipInfo(rel_path)

        # Normalize permission bits to either 755 (executable) or 644
        st_mode = os.stat(full_path).st_mode

        if stat.S_ISDIR(st_mode):
            zinfo.external_attr |= 0x10  # MS-DOS directory flag

        hashsum = hashlib.sha256()
        with open(full_path, "rb") as src:
            while True:
                buf = src.read(1024 * 8)
                if not buf:
                    break
                hashsum.update(buf)

            src.seek(0)
            wheel.writestr(zinfo, src.read(), compress_type=zipfile.ZIP_DEFLATED)

        size = os.stat(full_path).st_size
        hash_digest = urlsafe_b64encode(hashsum.digest()).decode("ascii").rstrip("=")

        self._records.append((rel_path, hash_digest, str(size)))

    def _write_metadata_file(self, fp):
        fp.write(self.format_pkginfo())

    def _write_wheel_file(self, fp):
        fp.write(
            WHEEL_FILE_FORMAT.format(
                version=context.version, pure_lib=self.meta.build is None, tag=self.tag
            )
        )

    def _write_entry_points(self, fp):
        entry_points = self.meta.entry_points
        for group_name in sorted(entry_points):
            fp.write("[{}]\n".format(group_name))
            for ep in sorted(entry_points[group_name]):
                fp.write(ep.replace(" ", "") + "\n")

            fp.write("\n")
