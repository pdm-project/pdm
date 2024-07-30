from __future__ import annotations

import argparse
from collections import defaultdict
from typing import TYPE_CHECKING

from pdm.cli.commands.base import BaseCommand
from pdm.cli.filters import GroupSelection
from pdm.cli.hooks import HookManager
from pdm.cli.options import (
    frozen_lockfile_option,
    groups_group,
    install_group,
    lockfile_option,
    override_option,
    prerelease_option,
    save_strategy_group,
    skip_option,
    unconstrained_option,
    update_strategy_group,
    venv_option,
)
from pdm.exceptions import PdmUsageError, ProjectError

if TYPE_CHECKING:
    from typing import Collection

    from pdm.models.requirements import Requirement
    from pdm.project import Project


class Command(BaseCommand):
    """Update package(s) in pyproject.toml"""

    arguments = (
        *BaseCommand.arguments,
        groups_group,
        install_group,
        lockfile_option,
        frozen_lockfile_option,
        save_strategy_group,
        override_option,
        update_strategy_group,
        prerelease_option,
        unconstrained_option,
        skip_option,
        venv_option,
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-t",
            "--top",
            action="store_true",
            help="Only update those listed in pyproject.toml",
        )
        parser.add_argument(
            "--dry-run",
            "--outdated",
            action="store_true",
            dest="dry_run",
            help="Show the difference only without modifying the lockfile content",
        )
        parser.add_argument(
            "--no-sync",
            dest="sync",
            default=True,
            action="store_false",
            help="Only update lock file but do not sync packages",
        )
        parser.add_argument("packages", nargs="*", help="If packages are given, only update them")
        parser.set_defaults(dev=None)

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        self.do_update(
            project,
            selection=GroupSelection.from_options(project, options),
            save=options.save_strategy or project.config["strategy.save"],
            strategy=options.update_strategy or project.config["strategy.update"],
            unconstrained=options.unconstrained,
            top=options.top,
            dry_run=options.dry_run,
            packages=options.packages,
            sync=options.sync,
            no_editable=options.no_editable,
            no_self=options.no_self,
            prerelease=options.prerelease,
            fail_fast=options.fail_fast,
            hooks=HookManager(project, options.skip),
        )

    @staticmethod
    def do_update(
        project: Project,
        *,
        selection: GroupSelection,
        strategy: str = "reuse",
        save: str = "compatible",
        unconstrained: bool = False,
        top: bool = False,
        dry_run: bool = False,
        packages: Collection[str] = (),
        sync: bool = True,
        no_editable: bool = False,
        no_self: bool = False,
        prerelease: bool | None = None,
        fail_fast: bool = False,
        hooks: HookManager | None = None,
    ) -> None:
        """Update specified packages or all packages"""
        from itertools import chain

        from pdm.cli.actions import do_lock, do_sync
        from pdm.cli.utils import check_project_file, save_version_specifiers
        from pdm.models.specifiers import get_specifier
        from pdm.utils import normalize_name

        hooks = hooks or HookManager(project)
        check_project_file(project)
        if len(packages) > 0 and (top or len(selection.groups) > 1 or not selection.default):
            raise PdmUsageError(
                "packages argument can't be used together with multiple -G or " "--no-default or --top."
            )
        all_dependencies = project.all_dependencies
        updated_deps: dict[str, list[Requirement]] = defaultdict(list)
        locked_groups = project.lockfile.groups
        tracked_names: set[str] = set()
        if not packages:
            if prerelease is not None:
                raise PdmUsageError("--prerelease/--stable must be used with packages given")
            selection.validate()
            for group in selection:
                updated_deps[group] = list(all_dependencies[group])
            tracked_names.update(r.identify() for deps in updated_deps.values() for r in deps)
        else:
            group = selection.one()
            if locked_groups and group not in locked_groups:
                raise ProjectError(f"Requested group not in lockfile: {group}")
            dependencies = all_dependencies[group]
            for name in packages:
                normalized_name = normalize_name(name)
                matched_reqs = [d for d in dependencies if (d.key or "") == normalized_name]
                if not matched_reqs:
                    candidates = project.get_locked_repository().all_candidates
                    if normalized_name not in candidates:
                        raise ProjectError(
                            f"[req]{name}[/] does not exist in [primary]{group}[/] "
                            f"{'dev-' if selection.dev else ''}dependencies nor is a transitive dependency."
                        )
                    look_in_other_group = next(
                        (
                            g
                            for g, deps in all_dependencies.items()
                            if any(normalized_name == d.key for d in deps) and g != group
                        ),
                        None,
                    )
                    if look_in_other_group is not None:
                        raise ProjectError(
                            f"[req]{name}[/] does not exist in [primary]{group}[/], but exists in [primary]{look_in_other_group}[/]."
                            " Please specify the correct group with `-G/--group`."
                        )
                    tracked_names.add(normalized_name)
                else:
                    for req in matched_reqs:
                        req.prerelease = prerelease
                    updated_deps[group].extend(matched_reqs)
            tracked_names.update(r.identify() for deps in updated_deps.values() for r in deps)
            project.core.ui.echo(
                f"Updating {'[bold]global[/] ' if project.is_global else ''}packages: {', '.join(f'[req]{v}[/]' for v in tracked_names)}."
            )
        if unconstrained:
            for deps in updated_deps.values():
                for dep in deps:
                    dep.specifier = get_specifier("")
        reqs = [r for g, deps in all_dependencies.items() for r in deps if locked_groups is None or g in locked_groups]
        # Since dry run is always true in the locking,
        # we need to emit the hook manually with the real dry_run value
        hooks.try_emit("pre_lock", requirements=reqs, dry_run=dry_run)
        with hooks.skipping("pre_lock", "post_lock"):
            resolved = do_lock(
                project,
                strategy=strategy,
                tracked_names=tracked_names,
                requirements=reqs,
                dry_run=True,
                hooks=hooks,
                groups=locked_groups,
            )
        hooks.try_emit("post_lock", resolution=resolved, dry_run=dry_run)
        if unconstrained:
            # Need to update version constraints
            save_version_specifiers(chain.from_iterable(updated_deps.values()), resolved, save)
        if not dry_run:
            if unconstrained:
                for group, deps in updated_deps.items():
                    project.add_dependencies(deps, group, selection.dev or False)
            project.write_lockfile(project.lockfile._data, False)
        if sync or dry_run:
            do_sync(
                project,
                selection=selection,
                clean=False,
                dry_run=dry_run,
                requirements=[r for deps in updated_deps.values() for r in deps],
                tracked_names=[r.identify() for deps in updated_deps.values() for r in deps] if top else None,
                no_editable=no_editable,
                no_self=no_self or "default" not in selection,
                fail_fast=fail_fast,
                hooks=hooks,
            )
