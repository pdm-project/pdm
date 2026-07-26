from __future__ import annotations

import hashlib
from collections.abc import Collection, Iterable
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING

import tomlkit

from pdm.exceptions import PdmUsageError
from pdm.models.requirements import Requirement, parse_requirement
from pdm.utils import cd

if TYPE_CHECKING:
    from pdm.project.core import Project


class WorkspaceManager:
    """Manage workspace membership and workspace-derived project state."""

    def __init__(self, owner: Project) -> None:
        self.owner = owner

    @cached_property
    def project(self) -> Project | None:
        """Return the parent workspace project if the owner is a member."""
        if self.owner.is_global:
            return None
        for parent in self.owner.root.parents:
            if not parent.joinpath(self.owner.PYPROJECT_FILENAME).exists():
                continue
            project = self.owner.core.create_project(parent)
            if project.pyproject.settings.get("workspace") and project.workspace.has_member(self.owner.root):
                return project
        return None

    @property
    def parent_project(self) -> Project | None:
        """Return the nearest parent project that can host a workspace."""
        if self.owner.is_global:
            return None
        for parent in self.owner.root.parents:
            if parent.joinpath(self.owner.PYPROJECT_FILENAME).exists():
                return self.owner.core.create_project(parent)
        return None

    @property
    def is_root(self) -> bool:
        return bool(self.owner.pyproject.settings.get("workspace"))

    def iter_members(self) -> Iterable[Path]:
        """Iterate over resolved workspace member paths."""
        if self.owner.is_global:
            return
        workspace = self.owner.pyproject.settings.get("workspace") or {}
        members = workspace.get("members", [])
        seen: set[Path] = set()
        for pattern in members:
            paths = (
                self.owner.root.glob(pattern) if any(char in pattern for char in "*?[") else [self.owner.root / pattern]
            )
            for path in paths:
                path = path.resolve()
                if path in seen or not path.is_dir() or not path.joinpath(self.owner.PYPROJECT_FILENAME).is_file():
                    continue
                seen.add(path)
                yield path

    def has_member(self, path: str | Path) -> bool:
        candidate = Path(path).absolute().resolve()
        return any(candidate == member for member in self.iter_members())

    def iter_dependencies(self) -> Iterable[Requirement]:
        """Iterate over implicit editable requirements for workspace members."""
        workspace_project = self.project or self.owner
        if not workspace_project.workspace.is_root:
            return
        for member in workspace_project.workspace.iter_members():
            member_project = workspace_project.core.create_project(member)
            if not member_project.name or not member_project.is_distribution:
                continue
            with cd(workspace_project.root):
                req = parse_requirement("./" + member.relative_to(workspace_project.root).as_posix(), True)
                req.relocate(workspace_project.backend)  # type: ignore[attr-defined]
            req.name = member_project.name
            req.groups = ["default"]
            yield req

    def with_dependencies(
        self,
        requirements: Iterable[Requirement],
        *,
        exclude: Collection[str] | None = None,
    ) -> list[Requirement]:
        result = list(requirements)
        seen = {req.identify() for req in result}
        if exclude:
            seen.update(exclude)
        for req in self.iter_dependencies():
            if req.identify() in seen:
                continue
            result.append(req)
            seen.add(req.identify())
        return result

    def content_hash(self, algo: str = "sha256") -> str:
        """Return a project content hash including workspace members."""
        workspace_project = self.project or self.owner
        root_hash = workspace_project.pyproject.content_hash(algo)
        if not workspace_project.workspace.is_root:
            return root_hash

        hasher = hashlib.new(algo)
        hasher.update(root_hash.encode("utf-8"))
        root = workspace_project.root.resolve()
        for member in sorted(
            workspace_project.workspace.iter_members(),
            key=lambda path: path.relative_to(root).as_posix(),
        ):
            member_project = workspace_project.core.create_project(member)
            member_path = member.relative_to(root).as_posix()
            hasher.update(b"\0")
            hasher.update(member_path.encode("utf-8"))
            hasher.update(b"\0")
            hasher.update(member_project.pyproject.content_hash(algo).encode("utf-8"))
        return hasher.hexdigest()

    def add_member(self, path: str | Path, *, show_message: bool = True, dry_run: bool = False) -> None:
        if workspace_project := self.project:
            workspace_project.workspace.add_member(path, show_message=show_message, dry_run=dry_run)
            return
        member = Path(path).absolute().resolve()
        try:
            member_path = member.relative_to(self.owner.root.resolve()).as_posix()
        except ValueError as e:
            raise PdmUsageError(f"Workspace member {member} must be under {self.owner.root}") from e
        self.owner.pyproject.open_for_write()
        members = self.owner.pyproject.settings.setdefault("workspace", {}).setdefault("members", tomlkit.array())
        if member_path not in (str(item) for item in members):
            members.append(member_path)
            if not dry_run:
                self.owner.pyproject.write(show_message=show_message)

    def remove_member(self, path: str | Path, *, show_message: bool = True, dry_run: bool = False) -> bool:
        if workspace_project := self.project:
            return workspace_project.workspace.remove_member(path, show_message=show_message, dry_run=dry_run)
        member = Path(path).absolute().resolve()
        try:
            member_path = member.relative_to(self.owner.root.resolve()).as_posix()
        except ValueError:
            return False
        self.owner.pyproject.open_for_write()
        workspace = self.owner.pyproject.settings.get("workspace")
        if not workspace:
            return False
        members = workspace.get("members", [])
        removed = False
        for index in reversed([i for i, item in enumerate(members) if str(item) == member_path]):
            del members[index]
            removed = True
        if removed and not dry_run:
            self.owner.pyproject.write(show_message=show_message)
        return removed

    def maybe_add(self) -> Project | None:
        """Add the owner to the nearest parent workspace when applicable."""
        if self.project is not None:
            return self.project
        if project := self.parent_project:
            project.workspace.add_member(self.owner.root)
            self.__dict__.pop("project", None)
            self.owner._lockfile = None
            self.owner._environment = None
            return project
        return None
