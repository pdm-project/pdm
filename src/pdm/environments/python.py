import os

from pdm.environments.base import BaseEnvironment
from pdm.models.in_process import get_sys_config_paths
from pdm.utils import get_venv_like_prefix


class PythonEnvironment(BaseEnvironment):
    """A project environment that is directly derived from a Python interpreter"""

    def get_paths(self) -> dict[str, str]:
        is_venv = self.interpreter.is_venv
        paths = get_sys_config_paths(
            str(self.interpreter.executable),
            kind="user"
            if not is_venv and self.project.global_config["global_project.user_site"]
            else "default",
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
