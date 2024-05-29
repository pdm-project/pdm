from __future__ import annotations

import argparse
import os
import shutil
import tarfile
import tempfile
from typing import Mapping

from pdm.cli.commands.base import BaseCommand
from pdm.cli.hooks import HookManager
from pdm.cli.options import (
    config_setting_option,
    no_isolation_option,
    project_option,
    skip_option,
    verbose_option,
)
from pdm.exceptions import ProjectError
from pdm.project import Project


class Command(BaseCommand):
    """Build artifacts for distribution"""

    arguments = (verbose_option, project_option, no_isolation_option, skip_option, config_setting_option)

    @staticmethod
    def do_build(
        project: Project,
        sdist: bool = True,
        wheel: bool = True,
        dest: str = "dist",
        clean: bool = True,
        config_settings: Mapping[str, str] | None = None,
        hooks: HookManager | None = None,
    ) -> None:
        """Build artifacts for distribution."""
        from pdm.builders import SdistBuilder, WheelBuilder

        hooks = hooks or HookManager(project)
        config_settings = project.core.state.config_settings

        if project.is_global:
            raise ProjectError("Not allowed to build based on the global project.")
        if not project.is_distribution:  # pragma: no cover
            raise ProjectError("tool.pdm.distribution must be `true` to be built.")
        if not wheel and not sdist:
            project.core.ui.echo("All artifacts are disabled, nothing to do.", err=True)
            return
        if not os.path.isabs(dest):
            dest = project.root.joinpath(dest).as_posix()
        if clean:
            shutil.rmtree(dest, ignore_errors=True)
        if not os.path.exists(dest):
            os.makedirs(dest, exist_ok=True)
        hooks.try_emit("pre_build", dest=dest, config_settings=config_settings)
        artifacts: list[str] = []
        with project.core.ui.logging("build"):
            if sdist:
                project.core.ui.echo("[info]Building sdist...")
                sdist_file = SdistBuilder(project.root, project.environment).build(dest)
                project.core.ui.echo(f"[info]Built sdist at {sdist_file}")
                artifacts.append(sdist_file)
            if wheel:
                if sdist:
                    project.core.ui.echo("[info]Building wheel from sdist...")
                    sdist_out = tempfile.mkdtemp(prefix="pdm-build-via-sdist-")
                    try:
                        with tarfile.open(sdist_file, "r:gz") as tf:
                            tf.extractall(sdist_out)
                            sdist_name = os.path.basename(sdist_file)[: -len(".tar.gz")]
                            whl = WheelBuilder(os.path.join(sdist_out, sdist_name), project.environment).build(dest)
                            project.core.ui.echo(f"[info]Built wheel at {whl}")
                            artifacts.append(whl)
                    finally:
                        shutil.rmtree(sdist_out, ignore_errors=True)
                else:
                    project.core.ui.echo("[info]Building wheel...")
                    whl = WheelBuilder(project.root, project.environment).build(dest)
                    project.core.ui.echo(f"[info]Built wheel at {whl}")
                    artifacts.append(whl)
        hooks.try_emit("post_build", artifacts=artifacts, config_settings=config_settings)

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--no-sdist",
            dest="sdist",
            default=True,
            action="store_false",
            help="Don't build source tarballs",
        )
        parser.add_argument(
            "--no-wheel",
            dest="wheel",
            default=True,
            action="store_false",
            help="Don't build wheels",
        )
        parser.add_argument("-d", "--dest", default="dist", help="Target directory to put artifacts")
        parser.add_argument(
            "--no-clean",
            dest="clean",
            default=True,
            action="store_false",
            help="Do not clean the target directory",
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        self.do_build(
            project,
            sdist=options.sdist,
            wheel=options.wheel,
            dest=options.dest,
            clean=options.clean,
            hooks=HookManager(project, options.skip),
        )
