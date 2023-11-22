from __future__ import annotations

import contextlib
import datetime
import hashlib
import json
import os
import sys
import textwrap
import warnings
from typing import Any, Collection, Iterable, cast

from resolvelib.reporters import BaseReporter
from resolvelib.resolvers import ResolutionImpossible, ResolutionTooDeep, Resolver

from pdm import termui
from pdm.cli.filters import GroupSelection
from pdm.cli.hooks import HookManager
from pdm.cli.utils import (
    check_project_file,
    fetch_hashes,
    find_importable_files,
    format_lockfile,
    format_resolution_impossible,
    get_pep582_path,
    set_env_in_reg,
)
from pdm.environments import BareEnvironment
from pdm.exceptions import PdmUsageError, ProjectError
from pdm.models.candidates import Candidate
from pdm.models.requirements import Requirement, parse_requirement
from pdm.project import Project
from pdm.project.lockfile import FLAG_CROSS_PLATFORM, FLAG_DIRECT_MINIMAL_VERSIONS
from pdm.resolver import resolve
from pdm.utils import deprecation_warning


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
) -> dict[str, Candidate]:
    """Performs the locking process and update lockfile."""
    hooks = hooks or HookManager(project)
    check_project_file(project)
    lock_strategy = project.lockfile.apply_strategy_change(strategy_change or [])
    if refresh:
        locked_repo = project.locked_repository
        repo = project.get_repository()
        mapping: dict[str, Candidate] = {}
        dependencies: dict[tuple[str, str | None], list[Requirement]] = {}
        with project.core.ui.open_spinner("Re-calculating hashes..."):
            for key, candidate in locked_repo.packages.items():
                reqs, python_requires, summary = locked_repo.candidate_info[key]
                candidate.summary = summary
                candidate.requires_python = python_requires
                mapping[candidate.identify()] = candidate
                dependencies[candidate.dep_key] = list(map(parse_requirement, reqs))
            with project.core.ui.logging("lock"):
                for c in mapping.values():
                    c.hashes.clear()
                fetch_hashes(repo, mapping)
            lockfile = format_lockfile(
                project, mapping, dependencies, groups=project.lockfile.groups, strategy=lock_strategy
            )
        project.write_lockfile(lockfile)
        return mapping
    # TODO: multiple dependency definitions for the same package.

    provider = project.get_provider(
        strategy,
        tracked_names,
        ignore_compatibility=FLAG_CROSS_PLATFORM in lock_strategy,
        direct_minimal_versions=FLAG_DIRECT_MINIMAL_VERSIONS in lock_strategy,
    )
    if not requirements:
        requirements = [
            r for g, deps in project.all_dependencies.items() if groups is None or g in groups for r in deps.values()
        ]
    if FLAG_CROSS_PLATFORM not in lock_strategy:
        this_env = project.environment.marker_environment
        requirements = [req for req in requirements if not req.marker or req.marker.evaluate(this_env)]
    resolve_max_rounds = int(project.config["strategy.resolve_max_rounds"])
    ui = project.core.ui
    with ui.logging("lock"):
        # The context managers are nested to ensure the spinner is stopped before
        # any message is thrown to the output.
        try:
            with ui.open_spinner(title="Resolving dependencies") as spin:
                reporter = project.get_reporter(requirements, tracked_names, spin)
                resolver: Resolver = project.core.resolver_class(provider, reporter)
                hooks.try_emit("pre_lock", requirements=requirements, dry_run=dry_run)
                mapping, dependencies = resolve(
                    resolver,
                    requirements,
                    project.environment.python_requires,
                    resolve_max_rounds,
                )
                spin.update("Fetching hashes for resolved packages...")
                fetch_hashes(provider.repository, mapping)
        except ResolutionTooDeep:
            ui.echo(f"{termui.Emoji.LOCK} Lock failed", err=True)
            ui.echo(
                "The dependency resolution exceeds the maximum loop depth of "
                f"{resolve_max_rounds}, there may be some circular dependencies "
                "in your project. Try to solve them or increase the "
                f"[success]`strategy.resolve_max_rounds`[/] config.",
                err=True,
            )
            raise
        except ResolutionImpossible as err:
            ui.echo(f"{termui.Emoji.LOCK} Lock failed", err=True)
            ui.error(format_resolution_impossible(err))
            raise ResolutionImpossible("Unable to find a resolution") from None
        else:
            data = format_lockfile(project, mapping, dependencies, groups=groups, strategy=lock_strategy)
            if project.enable_write_lockfile:
                ui.echo(f"{termui.Emoji.LOCK} Lock successful")
            project.write_lockfile(data, write=not dry_run)
            hooks.try_emit("post_lock", resolution=mapping, dry_run=dry_run)

    return mapping


def resolve_candidates_from_lockfile(
    project: Project, requirements: Iterable[Requirement], cross_platform: bool = False
) -> dict[str, Candidate]:
    ui = project.core.ui
    resolve_max_rounds = int(project.config["strategy.resolve_max_rounds"])
    reqs = [
        req for req in requirements if not req.marker or req.marker.evaluate(project.environment.marker_environment)
    ]
    with ui.logging("install-resolve"):
        with ui.open_spinner("Resolving packages from lockfile...") as spinner:
            reporter = BaseReporter()
            provider = project.get_provider(for_install=True)
            if cross_platform:
                provider.repository.ignore_compatibility = True
            resolver: Resolver = project.core.resolver_class(provider, reporter)
            mapping, *_ = resolve(
                resolver,
                reqs,
                project.environment.python_requires,
                resolve_max_rounds,
                record_markers=cross_platform,
            )
            spinner.update("Fetching hashes for resolved packages...")
            fetch_hashes(provider.repository, mapping)
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
    candidates = resolve_candidates_from_lockfile(project, requirements)
    if tracked_names and dry_run:
        candidates = {name: c for name, c in candidates.items() if name in tracked_names}
    synchronizer = project.core.synchronizer_class(
        candidates,
        project.environment,
        clean=clean,
        dry_run=dry_run,
        no_editable=no_editable,
        install_self=not no_self and project.is_library,
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


def get_latest_version(project: Project) -> str | None:
    """Get the latest version of PDM from PyPI, cache for 7 days"""
    cache_key = hashlib.sha224(sys.executable.encode()).hexdigest()
    cache_file = project.cache("self-check") / cache_key
    state = {}
    with contextlib.suppress(OSError):
        state = json.loads(cache_file.read_text())
    current_time = datetime.datetime.utcnow().timestamp()
    if state.get("last-check") and current_time - state["last-check"] < 60 * 60 * 24 * 7:
        return cast(str, state["latest-version"])
    try:
        latest_version = get_latest_pdm_version_from_pypi(project)
    except Exception as e:
        warnings.warn(f"Failed to get latest version: {e}", RuntimeWarning, stacklevel=1)
        latest_version = None
    if latest_version is None:
        return None
    state.update({"latest-version": latest_version, "last-check": current_time})
    with contextlib.suppress(OSError):
        cache_file.write_text(json.dumps(state))
    return latest_version


def check_update(project: Project) -> None:  # pragma: no cover
    """Check if there is a new version of PDM available"""
    from packaging.version import Version

    from pdm.cli.utils import is_homebrew_installation, is_pipx_installation, is_scoop_installation

    if project.core.ui.verbosity < termui.Verbosity.NORMAL:
        return

    this_version = project.core.version
    latest_version = get_latest_version(project)
    if latest_version is None or Version(this_version) >= Version(latest_version):
        return
    disable_command = "pdm config check_update false"

    is_prerelease = Version(latest_version).is_prerelease

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


# Moved functions
def do_add(*args: Any, **kwargs: Any) -> None:  # pragma: no cover
    from pdm.cli.commands.add import Command as AddCommand

    deprecation_warning(
        "`pdm.actions.do_add` has been moved to `pdm.cli.commands.add:Command.do_add` method, "
        "This function will be removed in the future.",
        stacklevel=2,
    )
    AddCommand().do_add(*args, **kwargs)


def do_update(*args: Any, **kwargs: Any) -> None:  # pragma: no cover
    from pdm.cli.commands.update import Command as UpdateCommand

    deprecation_warning(
        "`pdm.actions.do_update` has been moved to `pdm.cli.commands.update:Command.do_update` method, "
        "This function will be removed in the future.",
        stacklevel=2,
    )
    UpdateCommand().do_update(*args, **kwargs)


def do_use(*args: Any, **kwargs: Any) -> None:  # pragma: no cover
    from pdm.cli.commands.use import Command as UseCommand

    deprecation_warning(
        "`pdm.actions.do_use` has been moved to `pdm.cli.commands.use:Command.do_use` method, "
        "This function will be removed in the future.",
        stacklevel=2,
    )
    UseCommand().do_use(*args, **kwargs)


def do_remove(*args: Any, **kwargs: Any) -> None:  # pragma: no cover
    from pdm.cli.commands.remove import Command as RemoveCommand

    deprecation_warning(
        "`pdm.actions.do_remove` has been moved to `pdm.cli.commands.remove:Command.do_remove` method, "
        "This function will be removed in the future.",
        stacklevel=2,
    )
    RemoveCommand().do_remove(*args, **kwargs)


def do_import(*args: Any, **kwargs: Any) -> None:  # pragma: no cover
    from pdm.cli.commands.import_cmd import Command as ImportCommand

    deprecation_warning(
        "`pdm.actions.do_import` has been moved to `pdm.cli.commands.import_:Command.do_import` method, "
        "This function will be removed in the future.",
        stacklevel=2,
    )
    ImportCommand().do_import(*args, **kwargs)
