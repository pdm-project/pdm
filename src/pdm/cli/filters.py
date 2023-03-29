from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from pdm.compat import cached_property
from pdm.exceptions import PdmUsageError

if TYPE_CHECKING:
    from typing import Iterator, Sequence

    from pdm.project import Project


class GroupSelection:
    def __init__(
        self,
        project: Project,
        *,
        default: bool = True,
        dev: bool | None = None,
        groups: Sequence[str] = (),
        group: str | None = None,
    ):
        self.project = project
        self.groups = groups
        self.group = group
        self.default = default
        self.dev = dev

    @classmethod
    def from_options(cls, project: Project, options: argparse.Namespace) -> GroupSelection:
        if "group" in options:
            return cls(project, group=options.group, dev=options.dev)
        return cls(
            project,
            default=options.default,
            dev=options.dev,
            groups=options.groups,
        )

    def one(self) -> str:
        if self.group:
            return self.group
        if len(self.groups) == 1:
            return self.groups[0]
        return "dev" if self.dev else "default"

    @property
    def is_unset(self) -> bool:
        return self.default and self.dev is None and not self.groups

    def all(self) -> list[str] | None:
        if self.is_unset:
            if self.project.lockfile.exists():
                return self.project.lockfile.groups
        return list(self)

    @cached_property
    def _translated_groups(self) -> list[str]:
        """Translate default, dev and groups containing ":all" into a list of groups"""
        if self.is_unset:
            # Default case, return what is in the lock file
            locked_groups = self.project.lockfile.groups
            if locked_groups:
                return locked_groups
        default, dev, groups = self.default, self.dev, self.groups
        if dev is None:  # --prod is not set, include dev-dependencies
            dev = True
        project = self.project
        optional_groups = set(project.pyproject.metadata.get("optional-dependencies", {}))
        dev_groups = set(project.pyproject.settings.get("dev-dependencies", {}))
        groups_set = set(groups)
        if groups_set & dev_groups:
            if not dev:
                raise PdmUsageError("--prod is not allowed with dev groups and should be left")
        elif dev:
            groups_set.update(dev_groups)
        if ":all" in groups:
            groups_set.discard(":all")
            groups_set.update(optional_groups)

        invalid_groups = groups_set - set(project.iter_groups())
        if invalid_groups:
            project.core.ui.echo(
                "[d]Ignoring non-existing groups: [success]" f"{', '.join(invalid_groups)}[/]",
                err=True,
            )
            groups_set -= invalid_groups
        extra_groups = project.lockfile.compare_groups(groups_set)
        if extra_groups:
            raise PdmUsageError(f"Requested groups not in lockfile: {','.join(extra_groups)}")
        # Sorts the result in ascending order instead of in random order
        # to make this function pure
        result = sorted(groups_set)
        if default:
            result.insert(0, "default")
        return result

    def __iter__(self) -> Iterator[str]:
        return iter(self._translated_groups)

    def __contains__(self, group: str) -> bool:
        return group in self._translated_groups
