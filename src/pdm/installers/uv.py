from __future__ import annotations

import subprocess
from typing import Any

from pdm.environments.local import PythonLocalEnvironment
from pdm.exceptions import PdmUsageError
from pdm.installers.base import BaseSynchronizer
from pdm.models.repositories import LockedRepository
from pdm.termui import Verbosity


class UvSynchronizer(BaseSynchronizer):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        locked_repo = LockedRepository({}, self.environment.project.sources, self.environment)
        for package in self.packages:
            if self.no_editable and package.candidate.req.editable:
                package.candidate.req.editable = False
            locked_repo.add_package(package)
        self.locked_repo = locked_repo

    def synchronize(self) -> None:
        from pdm.formats.uv import uv_file_builder

        if isinstance(self.environment, PythonLocalEnvironment):
            raise PdmUsageError(
                "uv doesn't support PEP 582 local packages, this error occurs because you set use_uv = true."
            )

        if self.dry_run:
            self.environment.project.core.ui.echo("[warning]uv doesn't support dry run mode, skipping installation")
            return
        with uv_file_builder(
            self.environment.project, str(self.environment.python_requires), self.requirements, self.locked_repo
        ) as builder:
            builder.build_pyproject_toml()
            builder.build_uv_lock()
            cmd = self._get_sync_command()
            self.environment.project.core.ui.echo(f"Running uv sync command: {cmd}", verbosity=Verbosity.DETAIL)
            subprocess.run(cmd, check=True, cwd=self.environment.project.root)

    def _get_sync_command(self) -> list[str]:
        core = self.environment.project.core
        cmd = [
            *core.uv_cmd,
            "sync",
            "--all-extras",
            "--frozen",
            "-p",
            str(self.environment.interpreter.executable),
        ]
        if core.ui.verbosity > 0:
            cmd.append("--verbose")
        if not core.state.enable_cache:
            cmd.append("--no-cache")
        if not self.clean and not self.only_keep:
            cmd.append("--inexact")
        if self.reinstall:
            cmd.append("--reinstall")
        if not self.install_self:
            cmd.append("--no-install-project")
        first_index = True
        for source in self.environment.project.sources:
            assert source.url is not None
            if source.type == "find_links":
                cmd.extend(["--find-links", source.url])
            elif first_index:
                cmd.extend(["--index-url", source.url])
                first_index = False
            else:
                cmd.extend(["--extra-index-url", source.url])
        if self.use_install_cache:
            cmd.extend(["--link-mode", self.environment.project.config["install.cache_method"]])
        return cmd


class QuietUvSynchronizer(UvSynchronizer):
    def get_sync_command(self) -> list[str]:
        cmd = super()._get_sync_command()
        if "--verbose" in cmd:
            cmd.remove("--verbose")
        return [*cmd, "--quiet"]
