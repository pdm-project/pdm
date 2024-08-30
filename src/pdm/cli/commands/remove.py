from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, cast

from pdm.cli.commands.base import BaseCommand
from pdm.cli.filters import GroupSelection
from pdm.cli.hooks import HookManager
from pdm.cli.options import (
    dry_run_option,
    frozen_lockfile_option,
    install_group,
    lockfile_option,
    override_option,
    skip_option,
    venv_option,
)
from pdm.exceptions import PdmUsageError, ProjectError
from pdm.utils import normalize_name

if TYPE_CHECKING:
    from typing import Collection

    from pdm.project import Project


class Command(BaseCommand):
    """Remove packages from pyproject.toml"""

    arguments = (
        *BaseCommand.arguments,
        install_group,
        dry_run_option,
        lockfile_option,
        override_option,
        frozen_lockfile_option,
        skip_option,
        venv_option,
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-d",
            "--dev",
            default=False,
            action="store_true",
            help="Remove packages from dev dependencies",
        )
        parser.add_argument("-G", "--group", help="Specify the target dependency group to remove from")
        parser.add_argument(
            "--no-sync",
            dest="sync",
            default=True,
            action="store_false",
            help="Only write pyproject.toml and do not uninstall packages",
        )
        parser.add_argument("packages", nargs="+", help="Specify the packages to remove")

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        self.do_remove(
            project,
            selection=GroupSelection.from_options(project, options),
            sync=options.sync,
            packages=options.packages,
            no_editable=options.no_editable,
            no_self=options.no_self,
            dry_run=options.dry_run,
            fail_fast=options.fail_fast,
            hooks=HookManager(project, options.skip),
        )

    @staticmethod
    def do_remove(
        project: Project,
        selection: GroupSelection,
        sync: bool = True,
        packages: Collection[str] = (),
        no_editable: bool = False,
        no_self: bool = False,
        dry_run: bool = False,
        fail_fast: bool = False,
        hooks: HookManager | None = None,
    ) -> None:
        """Remove packages from working set and pyproject.toml"""
        from tomlkit.items import Array

        from pdm.cli.actions import do_lock, do_sync
        from pdm.cli.utils import check_project_file
        from pdm.models.requirements import parse_requirement
        from pdm.utils import cd

        hooks = hooks or HookManager(project)
        check_project_file(project)
        if not packages:
            raise PdmUsageError("Must specify at least one package to remove.")
        group = selection.one()
        lock_groups = project.lockfile.groups

        deps, setter = project.use_pyproject_dependencies(group, selection.dev or False)
        project.core.ui.echo(
            f"Removing {'[bold]global[/] ' if project.is_global else ''}packages from [primary]{group}[/] "
            f"{'dev-' if selection.dev else ''}dependencies: " + ", ".join(f"[req]{name}[/]" for name in packages)
        )
        tracked_names: set[str] = set()
        with cd(project.root):
            for name in packages:
                req = parse_requirement(name)
                matched_indexes = sorted((i for i, r in enumerate(deps) if req.matches(r)), reverse=True)
                if not matched_indexes:
                    raise ProjectError(f"[req]{name}[/] does not exist in [primary]{group}[/] dependencies.")
                for i in matched_indexes:
                    del deps[i]
                tracked_names.add(normalize_name(name))
        setter(cast(Array, deps).multiline(True))

        if not dry_run:
            project.pyproject.write()
        if lock_groups and group not in lock_groups:
            project.core.ui.warn(f"Group [success]{group}[/] isn't in lockfile, skipping lock.")
            return
        # It may remove the whole group, exclude it from lock groups first
        project_groups = project.iter_groups()
        if lock_groups is not None:
            lock_groups = [g for g in lock_groups if g in project_groups]
        do_lock(project, "reuse", dry_run=dry_run, tracked_names=tracked_names, hooks=hooks, groups=lock_groups)
        if sync:
            do_sync(
                project,
                selection=GroupSelection(project, default=False, groups=[group]),
                clean=True,
                no_editable=no_editable,
                no_self=no_self,
                dry_run=dry_run,
                fail_fast=fail_fast,
                hooks=hooks,
            )
