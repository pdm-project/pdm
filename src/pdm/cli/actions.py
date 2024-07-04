from __future__ import annotations

import contextlib
import dataclasses
import datetime
import hashlib
import inspect
import json
import os
import sys
import textwrap
from typing import TYPE_CHECKING, Collection, Iterable, cast

from resolvelib.reporters import BaseReporter
from resolvelib.resolvers import ResolutionImpossible, ResolutionTooDeep, Resolver

from pdm import termui
from pdm.cli.filters import GroupSelection
from pdm.cli.hooks import HookManager
from pdm.cli.utils import (
    check_project_file,
    fetch_hashes,
    find_importable_files,
    format_resolution_impossible,
    get_pep582_path,
    set_env_in_reg,
)
from pdm.environments import BareEnvironment
from pdm.exceptions import PdmException, PdmUsageError, ProjectError
from pdm.models.candidates import Candidate
from pdm.models.markers import EnvCompatibility, EnvSpec
from pdm.models.repositories import LockedRepository
from pdm.project import Project
from pdm.project.lockfile import FLAG_CROSS_PLATFORM, FLAG_DIRECT_MINIMAL_VERSIONS, FLAG_INHERIT_METADATA
from pdm.resolver import resolve
from pdm.termui import logger

if TYPE_CHECKING:
    from pdm.models.requirements import Requirement
    from pdm.resolver.providers import BaseProvider
    from pdm.resolver.reporters import SpinnerReporter


def do_lock(
    project: Project,
    strategy: str = "all",
    tracked_names: Iterable[str] | None = None,
    requirements: list[Requirement] | None = None,
    dry_run: bool = False,
    refresh: bool = False,
    groups: list[str] | None = None,
    strategy_change: list[str] | None = None,
    hooks: HookManager | None = None,
    env_spec: EnvSpec | None = None,
    append: bool = False,
) -> dict[str, list[Candidate]]:
    """Performs the locking process and update lockfile."""
    hooks = hooks or HookManager(project)
    check_project_file(project)
    if not project.config["strategy.inherit_metadata"]:
        project.lockfile.default_strategies.remove(FLAG_INHERIT_METADATA)
    lock_strategy = project.lockfile.apply_strategy_change(strategy_change or [])
    if FLAG_CROSS_PLATFORM in lock_strategy:
        # FIXME: add doc link
        project.core.ui.deprecated("`cross_platform` strategy is deprecated in favor of the new lock targets.")
    locked_repo = project.get_locked_repository()
    if refresh:
        if env_spec is not None:
            raise PdmUsageError("Cannot pass --python/--platform/--implementation with --refresh")
        repo = project.get_repository()
        with project.core.ui.open_spinner("Re-calculating hashes..."):
            with project.core.ui.logging("lock"):
                candidates = [entry.candidate for entry in locked_repo.packages.values()]
                for c in candidates:
                    c.hashes.clear()
                fetch_hashes(repo, candidates)
            lockfile = locked_repo.format_lockfile(groups=project.lockfile.groups, strategy=lock_strategy)
        project.write_lockfile(lockfile)
        return locked_repo.all_candidates

    if groups is None:
        groups = list(project.iter_groups())
    if not requirements:
        requirements = [r for group in groups for r in project.get_dependencies(group).values()]
    ui = project.core.ui
    supports_env_spec = "env_spec" in inspect.signature(project.get_provider).parameters
    # The repository to store the lock result
    if locked_repo.packages:
        result_repo = LockedRepository({}, sources=project.sources, environment=project.environment)
    else:
        # Use the same repository if the lock is empty.
        result_repo = locked_repo
    if not supports_env_spec:  # pragma: no cover
        ui.warn("Lock targets are not supported by the current provider")
        targets = [EnvSpec.allow_all() if FLAG_CROSS_PLATFORM in lock_strategy else project.environment.spec]
    elif FLAG_CROSS_PLATFORM in lock_strategy:
        if env_spec is not None:
            raise PdmUsageError("Cannot pass --python/--platform/--implementation with `cross_platform` strategy")
        if append:
            raise PdmUsageError("Cannot use `--append` with `cross_platform` strategy")
        targets = [EnvSpec.allow_all()]
    else:
        if append:
            if env_spec is None:
                raise PdmUsageError("Cannot use `--append` without --python/--platform/--implementation")
            if env_spec in locked_repo.targets:
                ui.echo(f"{termui.Emoji.LOCK} Lock target {env_spec} already exists, skip locking.")
                return locked_repo.all_candidates
            targets = [env_spec]
            result_repo = locked_repo
        else:
            targets = [env_spec] if env_spec else (locked_repo.targets[:] or project.lock_targets)
    # Restrict the target python to within the project's requires-python
    global_requires_python = project.environment.python_requires._logic
    for i, target in enumerate(targets):
        targets[i] = dataclasses.replace(target, requires_python=target.requires_python & global_requires_python)
    resolve_max_rounds = int(project.config["strategy.resolve_max_rounds"])
    hooks.try_emit("pre_lock", requirements=requirements, dry_run=dry_run)
    with ui.logging("lock"):
        # The context managers are nested to ensure the spinner is stopped before
        # any message is thrown to the output.
        try:
            with ui.open_spinner(title="Resolving dependencies") as spin:
                reporter = cast("SpinnerReporter", project.get_reporter(requirements, tracked_names, spin))
                for target in targets:
                    if supports_env_spec:
                        provider = project.get_provider(
                            strategy,
                            tracked_names,
                            direct_minimal_versions=FLAG_DIRECT_MINIMAL_VERSIONS in lock_strategy,
                            env_spec=target,
                            locked_repository=locked_repo,
                        )
                    else:  # pragma: no cover
                        provider = project.get_provider(
                            strategy,
                            tracked_names,
                            direct_minimal_versions=FLAG_DIRECT_MINIMAL_VERSIONS in lock_strategy,
                            ignore_compatibility=target.is_allow_all(),
                        )
                    mapping = _lock_for_env(
                        project, target, provider, reporter, requirements, lock_strategy, resolve_max_rounds
                    )
                    locked_repo.merge_result(target, mapping.values(), provider.fetched_dependencies)
                    if result_repo is not locked_repo:
                        result_repo.merge_result(target, mapping.values(), provider.fetched_dependencies)
        except ResolutionTooDeep:
            ui.echo(f"{termui.Emoji.LOCK} Lock failed.", err=True)
            ui.echo(
                "The dependency resolution exceeds the maximum loop depth of "
                f"{resolve_max_rounds}, there may be some circular dependencies "
                "in your project. Try to solve them or increase the "
                f"[success]`strategy.resolve_max_rounds`[/] config.",
                err=True,
            )
            raise
        except ResolutionImpossible as err:
            ui.echo(f"{termui.Emoji.LOCK} Lock failed.", err=True)
            ui.error(format_resolution_impossible(err))
            raise ResolutionImpossible("Unable to find a resolution") from None
        else:
            groups = list(set(groups) | provider.repository.collected_groups)
            provider.repository.collected_groups.clear()
            data = result_repo.format_lockfile(groups=groups, strategy=lock_strategy)
            if project.enable_write_lockfile:
                ui.echo(f"{termui.Emoji.LOCK} Lock successful.")
            project.write_lockfile(data, write=not dry_run)
            hooks.try_emit("post_lock", resolution=result_repo.all_candidates, dry_run=dry_run)

    return result_repo.all_candidates


def _lock_for_env(
    project: Project,
    env_spec: EnvSpec,
    provider: BaseProvider,
    reporter: SpinnerReporter,
    requirements: list[Requirement],
    lock_strategy: set[str],
    max_rounds: int,
) -> dict[str, Candidate]:
    reporter.spinner.update(
        f"Resolve for environment ({env_spec.requires_python}, {env_spec.platform}, {env_spec.implementation.name})"
    )
    requirements = [req for req in requirements if not req.marker or req.marker.matches(env_spec)]
    resolver: Resolver = project.core.resolver_class(provider, reporter)
    mapping, *_ = resolve(
        resolver,
        requirements,
        max_rounds,
        inherit_metadata=FLAG_INHERIT_METADATA in lock_strategy,
    )
    if project.enable_write_lockfile:
        fetch_hashes(provider.repository, mapping.values())
    return mapping


def resolve_candidates_from_lockfile(
    project: Project,
    requirements: Iterable[Requirement],
    groups: Collection[str] | None = None,
    env_spec: EnvSpec | None = None,
) -> dict[str, Candidate]:
    ui = project.core.ui
    resolve_max_rounds = int(project.config["strategy.resolve_max_rounds"])
    if env_spec is None:
        # Resolve for the current environment by default
        env_spec = project.environment.spec
    reqs = [req for req in requirements if not req.marker or req.marker.matches(env_spec)]
    with ui.open_spinner("Resolving packages from lockfile...") as spinner:
        reporter = BaseReporter()
        provider = project.get_provider(for_install=True, env_spec=env_spec)
        locked_repo = cast("LockedRepository", provider.repository)
        lock_targets = locked_repo.targets or project.lock_targets
        if FLAG_CROSS_PLATFORM not in project.lockfile.strategy and env_spec not in lock_targets:
            compatibilities = [target.compare(env_spec) for target in lock_targets]
            if not any(compat == EnvCompatibility.LE for compat in compatibilities):
                loose_compatible_target = next(
                    (
                        target
                        for (target, compat) in zip(lock_targets, compatibilities)
                        if compat == EnvCompatibility.GT
                    ),
                    None,
                )
                if loose_compatible_target is not None:
                    ui.warn(f"Found lock target {loose_compatible_target}, installing for env {env_spec}")
                else:
                    errors = [f"None of the lock targets matches the current env {env_spec}:"] + [
                        f" - {target}" for target in lock_targets
                    ]
                    ui.error("\n".join(errors))
                    raise PdmException("No compatible lock target found")

        with ui.logging("install-resolve"):
            if FLAG_INHERIT_METADATA in project.lockfile.strategy and groups is not None:
                return locked_repo.evaluate_candidates(groups)
            resolver: Resolver = project.core.resolver_class(provider, reporter)
            try:
                mapping, *_ = resolve(
                    resolver,
                    reqs,
                    resolve_max_rounds,
                    inherit_metadata=True,
                )
            except ResolutionImpossible as e:
                logger.exception("Broken lockfile")
                raise PdmException(
                    "Resolving from lockfile failed. You may fix the lockfile by `pdm lock --update-reuse` and retry."
                ) from e
            else:
                spinner.update("Fetching hashes for resolved packages...")
                fetch_hashes(provider.repository, mapping.values())
                return mapping


def check_lockfile(project: Project, raise_not_exist: bool = True) -> str | None:
    """Check if the lock file exists and is up to date. Return the lock strategy."""
    from pdm.project.lockfile import Compatibility

    if not project.lockfile.exists():
        if raise_not_exist:
            raise ProjectError("Lockfile does not exist, nothing to install")
        project.core.ui.warn("Lockfile does not exist")
        return "all"
    compat = project.lockfile.compatibility()
    if compat == Compatibility.NONE:
        project.core.ui.warn("Lockfile is not compatible with PDM")
        return "reuse"
    elif compat == Compatibility.BACKWARD:
        project.core.ui.warn("Lockfile is generated on an older version of PDM")
    elif compat == Compatibility.FORWARD:
        project.core.ui.warn("Lockfile is generated on a newer version of PDM")
    elif not project.is_lockfile_hash_match():
        project.core.ui.warn("Lockfile hash doesn't match pyproject.toml, packages may be outdated")
        return "reuse"
    return None


def do_sync(
    project: Project,
    *,
    selection: GroupSelection,
    dry_run: bool = False,
    clean: bool = False,
    requirements: list[Requirement] | None = None,
    tracked_names: Collection[str] | None = None,
    no_editable: bool | Collection[str] = False,
    no_self: bool = False,
    reinstall: bool = False,
    only_keep: bool = False,
    fail_fast: bool = False,
    hooks: HookManager | None = None,
) -> None:
    """Synchronize project"""
    hooks = hooks or HookManager(project)
    if requirements is None:
        requirements = []
        selection.validate()
        for group in selection:
            requirements.extend(project.get_dependencies(group).values())
    candidates = resolve_candidates_from_lockfile(project, requirements, groups=list(selection))
    if tracked_names and dry_run:
        candidates = {name: c for name, c in candidates.items() if name in tracked_names}
    synchronizer = project.core.synchronizer_class(
        candidates,
        project.environment,
        clean=clean,
        dry_run=dry_run,
        no_editable=no_editable,
        install_self=not no_self and project.is_distribution,
        reinstall=reinstall,
        only_keep=only_keep,
        fail_fast=fail_fast,
    )
    with project.core.ui.logging("install"):
        hooks.try_emit("pre_install", candidates=candidates, dry_run=dry_run)
        synchronizer.synchronize()
        hooks.try_emit("post_install", candidates=candidates, dry_run=dry_run)


def ask_for_import(project: Project) -> None:
    """Show possible importable files and ask user to decide"""
    from pdm.cli.commands.import_cmd import Command as ImportCommand

    importable_files = list(find_importable_files(project))
    if not importable_files:
        return
    project.core.ui.echo("Found following files from other formats that you may import:", style="primary")
    for i, (key, filepath) in enumerate(importable_files):
        project.core.ui.echo(f"{i}. [success]{filepath.as_posix()}[/] ({key})")
    project.core.ui.echo(f"{len(importable_files)}. [warning]don't do anything, I will import later.[/]")
    choice = termui.ask(
        "Please select",
        prompt_type=int,
        choices=[str(i) for i in range(len(importable_files) + 1)],
        show_choices=False,
    )
    if int(choice) == len(importable_files):
        return
    key, filepath = importable_files[int(choice)]
    ImportCommand.do_import(project, str(filepath), key, reset_backend=False)


def print_pep582_command(project: Project, shell: str = "AUTO") -> None:
    """Print the export PYTHONPATH line to be evaluated by the shell."""
    import shellingham

    pep582_path = get_pep582_path(project)
    ui = project.core.ui

    if os.name == "nt":
        try:
            set_env_in_reg("PYTHONPATH", pep582_path)
        except PermissionError:
            ui.error("Permission denied, please run the terminal as administrator.")
        ui.info("The environment variable has been saved, please restart the session to take effect.")
        return
    lib_path = pep582_path.replace("'", "\\'")
    if shell == "AUTO":
        shell = shellingham.detect_shell()[0]
    shell = shell.lower()
    if shell in ("zsh", "bash", "sh", "dash"):
        result = textwrap.dedent(
            f"""
            if [ -n "$PYTHONPATH" ]; then
                export PYTHONPATH='{lib_path}':$PYTHONPATH
            else
                export PYTHONPATH='{lib_path}'
            fi
            """
        ).strip()
    elif shell == "fish":
        result = f"set -x PYTHONPATH '{lib_path}' $PYTHONPATH"
    elif shell in ("tcsh", "csh"):
        result = textwrap.dedent(
            f"""
            if ( $?PYTHONPATH ) then
                if ( "$PYTHONPATH" != "" ) then
                    setenv PYTHONPATH '{lib_path}':$PYTHONPATH
                else
                    setenv PYTHONPATH '{lib_path}'
                endif
            else
                setenv PYTHONPATH '{lib_path}'
            endif
            """
        ).strip()
    else:
        raise PdmUsageError(f"Unsupported shell: {shell}, please specify another shell via `--pep582 <SHELL>`")
    ui.echo(result)


def get_latest_pdm_version_from_pypi(project: Project, prereleases: bool = False) -> str | None:
    """Get the latest version of PDM from PyPI."""
    environment = BareEnvironment(project)
    with environment.get_finder([project.default_source]) as finder:
        candidate = finder.find_best_match("pdm", allow_prereleases=prereleases).best
    return cast(str, candidate.version) if candidate else None


def get_latest_version(project: Project, expire_after: int = 7 * 24 * 3600) -> str | None:  # pragma: no cover
    """Get the latest version of PDM from PyPI, cache for 7 days"""
    cache_key = hashlib.sha224(sys.executable.encode()).hexdigest()
    cache_file = project.cache("self-check") / cache_key
    state = {}
    with contextlib.suppress(OSError):
        state = json.loads(cache_file.read_text())
    current_time = datetime.datetime.now(datetime.timezone.utc).timestamp()
    if (last_check := state.get("last-check")) and current_time - last_check < expire_after:
        return cast(str, state["latest-version"])
    try:
        latest_version = get_latest_pdm_version_from_pypi(project)
    except Exception as e:
        project.core.ui.warn(f"Failed to get latest version: {e}", verbosity=termui.Verbosity.NORMAL)
        latest_version = None
    if latest_version is None:
        return None
    state.update({"latest-version": latest_version, "last-check": current_time})
    with contextlib.suppress(OSError):
        cache_file.write_text(json.dumps(state))
    return latest_version


def check_update(project: Project) -> None:  # pragma: no cover
    """Check if there is a new version of PDM available"""
    from pdm.cli.utils import is_homebrew_installation, is_pipx_installation, is_scoop_installation
    from pdm.utils import parse_version

    if project.core.ui.verbosity < termui.Verbosity.NORMAL:
        return

    this_version = project.core.version
    latest_version = get_latest_version(project)
    if latest_version is None or parse_version(this_version) >= parse_version(latest_version):
        return
    disable_command = "pdm config check_update false"

    is_prerelease = parse_version(latest_version).is_prerelease

    if is_pipx_installation():
        install_command = f"pipx upgrade {'--pip-args=--pre ' if is_prerelease else ''}pdm"
    elif is_homebrew_installation():
        install_command = "brew upgrade pdm"
    elif is_scoop_installation():
        install_command = "scoop update pdm"
    else:
        install_command = "pdm self update" + (" --pre" if is_prerelease else "")
        if os.name == "nt":
            # On Windows, the executable can't replace itself, we add the python prefix to the command
            # A bit ugly but it works
            install_command = f"{sys.executable} -m {install_command}"

    message = [
        f"PDM [primary]{this_version}[/]",
        f" is installed, while [primary]{latest_version}[/]",
        " is available.\n",
        f"Please run [req]`{install_command}`[/]",
        " to upgrade.\n",
        f"Run [req]`{disable_command}`[/]",
        " to disable the check.",
    ]
    project.core.ui.info("".join(message))
