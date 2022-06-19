from __future__ import annotations

from typing import Any

from pdm import signals
from pdm.project.core import Project
from pdm.utils import cached_property

KNOWN_HOOKS = (
    "post_init",
    "pre_build",
    "post_build",
    "pre_install",
    "post_install",
    "pre_lock",
    "post_lock",
    "pre_publish",
    "post_publish",
)


class HookManager:
    projet: Project
    skip: list[str]

    def __init__(self, project: Project, skip: list[str] | None = None):
        self.project = project
        self.skip = skip or []

    @cached_property
    def skip_all(self) -> bool:
        return ":all" in self.skip

    @cached_property
    def skip_pre(self) -> bool:
        return ":pre" in self.skip

    @cached_property
    def skip_post(self) -> bool:
        return ":post" in self.skip

    def should_run(self, name: str) -> bool:
        """
        Tells wether a task given its name should run or not
        according to the current skipping rules.
        """
        return (
            not self.skip_all
            and name not in self.skip
            and not (self.skip_pre and name.startswith("pre_"))
            and not (self.skip_post and name.startswith("post_"))
        )

    def try_emit(self, name: str, **kwargs: Any) -> None:
        """
        Emit a hook signal if rules allow it.
        """
        if self.should_run(name):
            getattr(signals, name).send(self.project, hooks=self, **kwargs)
