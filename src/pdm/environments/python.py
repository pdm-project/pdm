from __future__ import annotations

import os
from typing import TYPE_CHECKING

from pdm.environments.base import BaseEnvironment
from pdm.models.in_process import get_sys_config_paths
from pdm.models.working_set import WorkingSet

if TYPE_CHECKING:
    from pdm.project import Project


class PythonEnvironment(BaseEnvironment):
    """A project environment that is directly derived from a Python interpreter"""

    def __init__(
        self,
        project: Project,
        *,
        python: str | None = None,
        prefix: str | None = None,
        extra_paths: list[str] | None = None,
    ) -> None:
        super().__init__(project, python=python)
        self.prefix = prefix
        self.extra_paths = extra_paths or []

    def get_paths(self, dist_name: str | None = None) -> dict[str, str]:
        is_venv = self.interpreter.get_venv() is not None
        if self.prefix is not None:
            replace_vars = {"base": self.prefix, "platbase": self.prefix}
            kind = "prefix"
        else:
            replace_vars = None
            kind = "user" if not is_venv and self.project.global_config["global_project.user_site"] else "default"
        paths = get_sys_config_paths(str(self.interpreter.executable), replace_vars, kind=kind)
        if is_venv:
            python_xy = f"python{self.interpreter.identifier}"
            paths["include"] = os.path.join(paths["data"], "include", "site", python_xy)
        elif not dist_name:
            dist_name = "UNKNOWN"
        if dist_name:
            paths["include"] = os.path.join(paths["include"], dist_name)
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

    def get_working_set(self) -> WorkingSet:
        scheme = self.get_paths()
        paths = [scheme["platlib"], scheme["purelib"]]
        venv = self.interpreter.get_venv()
        shared_paths = self.extra_paths[:]
        if venv is not None and venv.include_system_site_packages:
            shared_paths.extend(venv.base_paths)
        return WorkingSet(paths, shared_paths=list(dict.fromkeys(shared_paths)))
