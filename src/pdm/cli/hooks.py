from __future__ import annotations

import contextlib
from typing import Any, Generator

from blinker import Signal

from pdm import signals
from pdm.project.core import Project

KNOWN_HOOKS = tuple(name for name, obj in signals.__dict__.items() if isinstance(obj, Signal))


class HookManager:
    def __init__(self, project: Project, skip: list[str] | None = None):
        self.project = project
        self.skip = skip or []

    @contextlib.contextmanager
    def skipping(self, *names: str) -> Generator[None, None, None]:
        """
        Temporarily skip some hooks.
        """
        old_skip = self.skip[:]
        self.skip.extend(names)
        yield
        self.skip = old_skip

    @property
    def skip_all(self) -> bool:
        return ":all" in self.skip

    @property
    def skip_pre(self) -> bool:
        return ":pre" in self.skip

    @property
    def skip_post(self) -> bool:
        return ":post" in self.skip

    def should_run(self, name: str) -> bool:
        """
        Tells whether a task given its name should run or not
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
