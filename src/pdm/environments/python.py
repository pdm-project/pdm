from __future__ import annotations

import os
from typing import TYPE_CHECKING

from pdm.environments.base import BaseEnvironment
from pdm.models.in_process import get_sys_config_paths

if TYPE_CHECKING:
    from pdm.project import Project


class PythonEnvironment(BaseEnvironment):
    """A project environment that is directly derived from a Python interpreter"""

    def __init__(self, project: Project, *, python: str | None = None, prefix: str | None = None) -> None:
        super().__init__(project, python=python)
        self.prefix = prefix

    def get_paths(self) -> dict[str, str]:
        is_venv = self.interpreter.get_venv() is not None
        if self.prefix is not None:
            replace_vars = {"base": self.prefix, "platbase": self.prefix}
            kind = "prefix"
        else:
            replace_vars = None
            kind = "user" if not is_venv and self.project.global_config["global_project.user_site"] else "default"
        paths = get_sys_config_paths(str(self.interpreter.executable), replace_vars, kind=kind)
        if is_venv and self.prefix is None:
            python_xy = f"python{self.interpreter.identifier}"
            paths["include"] = os.path.join(paths["data"], "include", "site", python_xy)
        paths["prefix"] = paths["data"]
        paths["headers"] = paths["include"]
        return paths

    @property
    def process_env(self) -> dict[str, str]:
        env = super().process_env
        venv = self.interpreter.get_venv()
        if venv is not None and self.prefix is None:
            env.update(venv.env_vars())
        return env
