from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from pdm.cli.commands.base import BaseCommand
from pdm.cli.filters import GroupSelection
from pdm.cli.hooks import HookManager
from pdm.cli.options import (
    dry_run_option,
    frozen_lockfile_option,
    install_group,
    lockfile_option,
    override_option,
    packages_group,
    prerelease_option,
    save_strategy_group,
    skip_option,
    unconstrained_option,
    update_strategy_group,
    venv_option,
)
from pdm.exceptions import PdmUsageError

if TYPE_CHECKING:
    from typing import Collection

    from pdm.models.requirements import Requirement
    from pdm.project import Project


class Command(BaseCommand):
    """Add package(s) to pyproject.toml and install them"""

    arguments = (
        *BaseCommand.arguments,
        lockfile_option,
        frozen_lockfile_option,
        save_strategy_group,
        override_option,
        update_strategy_group,
        prerelease_option,
        unconstrained_option,
        packages_group,
        install_group,
        dry_run_option,
        venv_option,
        skip_option,
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-d",
            "--dev",
            default=False,
            action="store_true",
            help="Add packages into dev dependencies",
        )
        parser.add_argument("-G", "--group", help="Specify the target dependency group to add into")
        parser.add_argument(
            "--no-sync",
            dest="sync",
            default=True,
            action="store_false",
            help="Only write pyproject.toml and do not sync the working set",
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        if options.editables and options.no_editable:
            raise PdmUsageError("`--no-editable` cannot be used with `-e/--editable`")
        self.do_add(
            project,
            selection=GroupSelection.from_options(project, options),
            sync=options.sync,
            save=options.save_strategy or project.config["strategy.save"],
            strategy=options.update_strategy or project.config["strategy.update"],
            editables=options.editables,
            packages=options.packages,
            unconstrained=options.unconstrained,
            no_editable=options.no_editable,
            no_self=options.no_self,
            dry_run=options.dry_run,
            prerelease=options.prerelease,
            fail_fast=options.fail_fast,
            hooks=HookManager(project, options.skip),
        )

    @staticmethod
    def do_add(
        project: Project,
        *,
        selection: GroupSelection,
        sync: bool = True,
        save: str = "compatible",
        strategy: str = "reuse",
        editables: Collection[str] = (),
        packages: Collection[str] = (),
        unconstrained: bool = False,
        no_editable: bool = False,
        no_self: bool = False,
        dry_run: bool = False,
        prerelease: bool | None = None,
        fail_fast: bool = False,
        hooks: HookManager | None = None,
    ) -> None:
        """Add packages and install"""
        from pdm.cli.actions import do_lock, do_sync
        from pdm.cli.utils import check_project_file, save_version_specifiers
        from pdm.models.requirements import parse_requirement
        from pdm.models.specifiers import get_specifier
        from pdm.utils import normalize_name

        hooks = hooks or HookManager(project)
        check_project_file(project)
        if editables and no_editable:
            raise PdmUsageError("Cannot use --no-editable with editable packages given.")
        group = selection.one()
        tracked_names: set[str] = set()
        requirements: list[Requirement] = []
        lock_groups = ["default"] if project.lockfile.empty() else project.lockfile.groups
        if lock_groups is not None and group not in lock_groups:
            if project.enable_write_lockfile:
                project.core.ui.info(f"Adding group [success]{group}[/] to lockfile")
            lock_groups.append(group)
        if (
            group == "default"
            or not selection.dev
            and group not in project.pyproject.settings.get("dev-dependencies", {})
        ):
            if editables:
                raise PdmUsageError("Cannot add editables to the default or optional dependency group")
        for r in [parse_requirement(line, True) for line in editables] + [parse_requirement(line) for line in packages]:
            if project.is_distribution and normalize_name(name := project.name) == r.key and not r.extras:
                project.core.ui.warn(f"Package [req]{name}[/] is the project itself.")
                continue
            if r.is_file_or_url:
                r.relocate(project.backend)  # type: ignore[attr-defined]
            key = r.identify()
            r.prerelease = prerelease
            tracked_names.add(key)
            requirements.append(r)
        if requirements:
            project.core.ui.echo(
                f"Adding {'[bold]global[/] ' if project.is_global else ''}packages to [primary]{group}[/] "
                f"{'dev-' if selection.dev else ''}dependencies: "
                + ", ".join(f"[req]{r.as_line()}[/]" for r in requirements)
            )
        group_deps = project.add_dependencies(requirements, group, selection.dev or False, write=False)
        all_dependencies = project.all_dependencies
        all_dependencies[group] = group_deps
        if unconstrained:
            if not requirements:
                raise PdmUsageError("--unconstrained requires at least one package")
            for req in group_deps:
                req.specifier = get_specifier("")

        reqs = [r for g, deps in all_dependencies.items() for r in deps if lock_groups is None or g in lock_groups]
        with hooks.skipping("post_lock"):
            resolved = do_lock(
                project,
                strategy,
                tracked_names,
                reqs,
                dry_run=True,
                hooks=hooks,
                groups=lock_groups,
            )

        # Update dependency specifiers and lockfile hash.
        deps_to_update = group_deps if unconstrained else requirements
        save_version_specifiers(deps_to_update, resolved, save)
        hooks.try_emit("post_lock", resolution=resolved, dry_run=dry_run)
        if not dry_run:
            project.add_dependencies(deps_to_update, group, selection.dev or False)
            project.write_lockfile(project.lockfile._data, False)
        if sync:
            do_sync(
                project,
                selection=GroupSelection(project, groups=[group], default=False),
                no_editable=no_editable and tracked_names,
                no_self=no_self or group != "default",
                requirements=group_deps,
                dry_run=dry_run,
                fail_fast=fail_fast,
                hooks=hooks,
            )
