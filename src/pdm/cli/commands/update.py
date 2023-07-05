from __future__ import annotations

import argparse
from collections import defaultdict
from typing import TYPE_CHECKING

from pdm.cli.commands.base import BaseCommand
from pdm.cli.filters import GroupSelection
from pdm.cli.hooks import HookManager
from pdm.cli.options import (
    groups_group,
    install_group,
    lockfile_option,
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
        save_strategy_group,
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
        prerelease: bool = False,
        fail_fast: bool = False,
        hooks: HookManager | None = None,
    ) -> None:
        """Update specified packages or all packages"""
        from itertools import chain

        from pdm.cli.actions import do_lock, do_sync
        from pdm.cli.utils import check_project_file, populate_requirement_names, save_version_specifiers
        from pdm.models.requirements import strip_extras
        from pdm.models.specifiers import get_specifier
        from pdm.utils import normalize_name

        hooks = hooks or HookManager(project)
        check_project_file(project)
        if len(packages) > 0 and (top or len(selection.groups) > 1 or not selection.default):
            raise PdmUsageError(
                "packages argument can't be used together with multiple -G or " "--no-default or --top."
            )
        all_dependencies = project.all_dependencies
        updated_deps: dict[str, dict[str, Requirement]] = defaultdict(dict)
        locked_groups = project.lockfile.groups
        if not packages:
            if prerelease:
                raise PdmUsageError("--prerelease must be used with packages given")
            selection.validate()
            for group in selection:
                updated_deps[group] = all_dependencies[group]
        else:
            group = selection.one()
            if locked_groups and group not in locked_groups:
                raise ProjectError(f"Requested group not in lockfile: {group}")
            dependencies = all_dependencies[group]
            for name in packages:
                matched_name = next(
                    (k for k in dependencies if normalize_name(strip_extras(k)[0]) == normalize_name(name)),
                    None,
                )
                if not matched_name:
                    raise ProjectError(
                        f"[req]{name}[/] does not exist in [primary]{group}[/] "
                        f"{'dev-' if selection.dev else ''}dependencies."
                    )
                dependencies[matched_name].prerelease = prerelease
                updated_deps[group][matched_name] = dependencies[matched_name]
            project.core.ui.echo(
                "Updating packages: {}.".format(
                    ", ".join(f"[req]{v}[/]" for v in chain.from_iterable(updated_deps.values()))
                )
            )
        if unconstrained:
            for deps in updated_deps.values():
                for dep in deps.values():
                    dep.specifier = get_specifier("")
        reqs = [r for deps in all_dependencies.values() for r in deps.values()]
        # Since dry run is always true in the locking,
        # we need to emit the hook manually with the real dry_run value
        hooks.try_emit("pre_lock", requirements=reqs, dry_run=dry_run)
        with hooks.skipping("pre_lock", "post_lock"):
            resolved = do_lock(
                project,
                strategy,
                chain.from_iterable(updated_deps.values()),
                reqs,
                dry_run=True,
                hooks=hooks,
                groups=locked_groups,
            )
        hooks.try_emit("post_lock", resolution=resolved, dry_run=dry_run)
        for deps in updated_deps.values():
            populate_requirement_names(deps)
        if unconstrained:
            # Need to update version constraints
            save_version_specifiers(updated_deps, resolved, save)
            for group, deps in updated_deps.items():
                project.add_dependencies(deps, group, selection.dev or False)
        if not dry_run:
            project.write_lockfile(project.lockfile._data, False, groups=locked_groups)
        if sync or dry_run:
            do_sync(
                project,
                selection=selection,
                clean=False,
                dry_run=dry_run,
                requirements=[r for deps in updated_deps.values() for r in deps.values()],
                tracked_names=list(chain.from_iterable(updated_deps.values())) if top else None,
                no_editable=no_editable,
                no_self=no_self,
                fail_fast=fail_fast,
                hooks=hooks,
            )
