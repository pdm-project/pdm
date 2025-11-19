from __future__ import annotations

import os
import subprocess
from typing import Any

from pdm._types import HiddenText
from pdm.environments.local import PythonLocalEnvironment
from pdm.exceptions import PdmUsageError, ProjectError
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
        from itertools import chain

        from pdm.formats.uv import uv_file_builder

        if isinstance(self.environment, PythonLocalEnvironment):
            raise PdmUsageError(
                "uv doesn't support PEP 582 local packages, this error occurs because you set use_uv = true."
            )

        if self.dry_run:
            self.environment.project.core.ui.echo("[warning]uv doesn't support dry run mode, skipping installation")
            return
        if self.requirements is not None:
            requirements = list(self.requirements)
        else:
            requirements = list(chain.from_iterable(self.environment.project.all_dependencies.values()))
        with uv_file_builder(
            self.environment.project, str(self.environment.python_requires), requirements, self.locked_repo
        ) as builder:
            venv_project = self.environment.interpreter.get_venv()
            if venv_project is None:
                raise ProjectError("uv mode doesn't support non-virtual environments")
            builder.build_pyproject_toml()
            builder.build_uv_lock(include_self=self.install_self)
            cmd = self._get_sync_command()
            self.environment.project.core.ui.echo(f"Running uv sync command: {cmd}", verbosity=Verbosity.DETAIL)
            real_cmd = [s.secret if isinstance(s, HiddenText) else s for s in cmd]
            env = {**os.environ, "UV_PROJECT_ENVIRONMENT": str(venv_project.root)}
            subprocess.run(real_cmd, check=True, cwd=self.environment.project.root, env=env)

    def _get_sync_command(self) -> list[str | HiddenText]:
        core = self.environment.project.core
        cmd: list[str | HiddenText] = [
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
            url = source.url_with_credentials
            if source.type == "find_links":
                cmd.extend(["--find-links", url])
            elif first_index:
                cmd.extend(["--index-url", url])
                first_index = False
            else:
                cmd.extend(["--extra-index-url", url])
        if self.use_install_cache:
            cmd.extend(["--link-mode", self.environment.project.config["install.cache_method"]])
        return cmd


class QuietUvSynchronizer(UvSynchronizer):
    def _get_sync_command(self) -> list[str | HiddenText]:
        cmd = super()._get_sync_command()
        if "--verbose" in cmd:
            cmd.remove("--verbose")
        return [*cmd, "--quiet"]
