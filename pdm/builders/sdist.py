import os
import tarfile
import tempfile
from copy import copy

from pkg_resources import safe_version, to_filename

from pdm.builders.base import Builder
from pdm.iostream import stream


def normalize_file_permissions(st_mode):
    """
    Normalizes the permission bits in the st_mode field from stat to 644/755

    Popular VCSs only track whether a file is executable or not. The exact
    permissions can vary on systems with different umasks. Normalising
    to 644 (non executable) or 755 (executable) makes builds more reproducible.
    """
    # Set 644 permissions, leaving higher bits of st_mode unchanged
    new_mode = (st_mode | 0o644) & ~0o133
    if st_mode & 0o100:
        new_mode |= 0o111  # Executable: 644 -> 755

    return new_mode


def clean_tarinfo(tar_info):
    """
    Clean metadata from a TarInfo object to make it more reproducible.

        - Set uid & gid to 0
        - Set uname and gname to ""
        - Normalise permissions to 644 or 755
        - Set mtime if not None
    """
    ti = copy(tar_info)
    ti.uid = 0
    ti.gid = 0
    ti.uname = ""
    ti.gname = ""
    ti.mode = normalize_file_permissions(ti.mode)

    return ti


class SdistBuilder(Builder):
    """This build should be performed for PDM project only."""

    def build(self, build_dir: str, **kwargs):
        if not os.path.exists(build_dir):
            os.makedirs(build_dir, exist_ok=True)

        stream.echo("- Building {}...".format(stream.cyan("sdist")))
        version = to_filename(safe_version(self.meta.version))

        target = os.path.join(
            build_dir, "{}-{}.tar.gz".format(self.meta.project_name, version)
        )
        tar = tarfile.open(target, mode="w:gz", format=tarfile.PAX_FORMAT)

        try:
            tar_dir = "{}-{}".format(self.meta.project_name, version)

            files_to_add = self.find_files_to_add(True)

            for relpath in files_to_add:
                tar.add(
                    relpath,
                    arcname=os.path.join(tar_dir, str(relpath)),
                    recursive=False,
                )
                stream.echo(f" - Adding: {relpath}", verbosity=stream.DETAIL)

            fd, temp_name = tempfile.mkstemp(prefix="pkg-info")
            pkg_info = self.format_pkginfo(False).encode("utf-8")
            with open(fd, "wb") as f:
                f.write(pkg_info)
            tar.add(
                temp_name, arcname=os.path.join(tar_dir, "PKG-INFO"), recursive=False
            )
            stream.echo(" - Adding: PKG-INFO", verbosity=stream.DETAIL)
        finally:
            tar.close()

        stream.echo("- Built {}".format(stream.cyan(os.path.basename(target))))

        return target
