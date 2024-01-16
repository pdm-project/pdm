from __future__ import annotations

import argparse
import os
import shutil
from typing import Mapping

from pdm.cli.commands.base import BaseCommand
from pdm.cli.hooks import HookManager
from pdm.cli.options import (
    no_isolation_option,
    project_option,
    skip_option,
    verbose_option,
)
from pdm.exceptions import ProjectError
from pdm.project import Project


class Command(BaseCommand):
    """Build artifacts for distribution"""

    arguments = (verbose_option, project_option, no_isolation_option, skip_option)

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

        if project.is_global:
            raise ProjectError("Not allowed to build based on the global project.")
        if not project.is_library:  # pragma: no cover
            raise ProjectError("The package-type must be `library` to be built.")
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
                project.core.ui.echo("Building sdist...")
                loc = SdistBuilder(project.root, project.environment).build(dest, config_settings)
                project.core.ui.echo(f"Built sdist at {loc}")
                artifacts.append(loc)
            if wheel:
                project.core.ui.echo("Building wheel...")
                loc = WheelBuilder(project.root, project.environment).build(dest, config_settings)
                project.core.ui.echo(f"Built wheel at {loc}")
                artifacts.append(loc)
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
        parser.add_argument(
            "--config-setting",
            "-C",
            action="append",
            help="Pass options to the backend. options with a value must be "
            'specified after "=": `--config-setting=--opt(=value)` '
            "or `-C--opt(=value)`",
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        config_settings = None
        if options.config_setting:
            config_settings = {}
            for item in options.config_setting:
                name, _, value = item.partition("=")
                if name not in config_settings:
                    config_settings[name] = value
                else:
                    if not isinstance(config_settings[name], list):
                        config_settings[name] = [config_settings[name]]
                    config_settings[name].append(value)
        self.do_build(
            project,
            sdist=options.sdist,
            wheel=options.wheel,
            dest=options.dest,
            clean=options.clean,
            config_settings=config_settings,
            hooks=HookManager(project, options.skip),
        )
