import os
import tarfile
import time
from io import BytesIO

from pdm.builders.base import Builder
from pdm.context import context


class SdistBuilder(Builder):
    """This build should be performed for PDM project only."""

    def build(self, build_dir: str, **kwargs):
        if not os.path.exists(build_dir):
            os.makedirs(build_dir, exist_ok=True)

        context.io.echo("- Building {}...".format(context.io.cyan("sdist")))

        target = os.path.join(
            build_dir, "{}-{}.tar.gz".format(self.meta.project_name, self.meta.version)
        )
        tar = tarfile.open(target, mode="w:gz", format=tarfile.PAX_FORMAT)

        try:
            tar_dir = "{}-{}".format(self.meta.project_name, self.meta.version)

            files_to_add = self.find_files_to_add()

            for relpath in files_to_add:
                tar_info = tar.gettarinfo(
                    str(relpath), arcname=os.path.join(tar_dir, str(relpath))
                )
                context.io.echo(f" - Adding: {relpath}", verbosity=context.io.DETAIL)
                if tar_info.isreg():
                    with open(relpath, "rb") as f:
                        tar.addfile(tar_info, f)
                else:
                    tar.addfile(tar_info)  # Symlinks & ?

            pkg_info = self.format_pkginfo()

            tar_info = tarfile.TarInfo(os.path.join(tar_dir, "PKG-INFO"))
            tar_info.size = len(pkg_info)
            tar_info.mtime = time.time()
            context.io.echo(" - Adding: PKG-INFO", verbosity=context.io.DETAIL)
            tar.addfile(tar_info, BytesIO(pkg_info.encode("utf-8")))
        finally:
            tar.close()

        context.io.echo("- Built {}".format(context.io.cyan(os.path.basename(target))))

        return target
