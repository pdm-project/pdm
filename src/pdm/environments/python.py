from __future__ import annotations

import os
from typing import TYPE_CHECKING

from pdm.environments.base import BaseEnvironment
from pdm.models.in_process import get_sys_config_paths
from pdm.models.python import PythonInfo
from pdm.utils import get_venv_like_prefix

if TYPE_CHECKING:
    from pdm.project import Project


class PythonEnvironment(BaseEnvironment):
    """A project environment that is directly derived from a Python interpreter"""

    def __init__(self, project: Project, *, python: str | None = None) -> None:
        super().__init__(project)
        if python is None:
            self._interpreter = project.python
        else:
            self._interpreter = PythonInfo.from_path(python)

    @property
    def interpreter(self) -> PythonInfo:
        return self._interpreter

    def get_paths(self) -> dict[str, str]:
        is_venv = self.interpreter.is_venv
        paths = get_sys_config_paths(
            str(self.interpreter.executable),
            kind="user" if not is_venv and self.project.global_config["global_project.user_site"] else "default",
        )
        if is_venv:
            python_xy = f"python{self.interpreter.identifier}"
            paths["include"] = os.path.join(paths["data"], "include", "site", python_xy)
        paths["prefix"] = paths["data"]
        paths["headers"] = paths["include"]
        return paths

    @property
    def process_env(self) -> dict[str, str]:
        env = super().process_env
        if self.interpreter.is_venv:
            env["VIRTUAL_ENV"] = str(get_venv_like_prefix(self.interpreter.executable))
        return env
