from __future__ import annotations

from typing import TYPE_CHECKING

from pdm.environments.base import BaseEnvironment
from pdm.models.in_process import get_sys_config_paths

if TYPE_CHECKING:
    from pdm.project import Project


class PrefixEnvironment(BaseEnvironment):
    """An environment whose install scheme depends on the given prefix"""

    def __init__(self, project: Project, *, prefix: str) -> None:
        super().__init__(project)
        self.prefix = prefix

    def get_paths(self) -> dict[str, str]:
        paths = get_sys_config_paths(
            str(self.interpreter.executable),
            {"base": self.prefix, "platbase": self.prefix},
            kind="prefix",
        )
        paths["prefix"] = paths["data"]
        paths["headers"] = paths["include"]
        return paths
