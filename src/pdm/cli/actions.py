from __future__ import annotations

import contextlib
import datetime
import hashlib
import json
import os
import sys
import textwrap
import warnings
from argparse import Namespace
from collections import defaultdict
from itertools import chain
from typing import Collection, Iterable, cast

import tomlkit
from resolvelib.reporters import BaseReporter
from resolvelib.resolvers import ResolutionImpossible, ResolutionTooDeep, Resolver
from tomlkit.items import Array

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
    merge_dictionary,
    save_version_specifiers,
    set_env_in_reg,
)
from pdm.environments import BareEnvironment, PythonLocalEnvironment
from pdm.exceptions import NoPythonVersion, PdmUsageError, ProjectError
from pdm.models.backends import DEFAULT_BACKEND
from pdm.models.candidates import Candidate
from pdm.models.python import PythonInfo
from pdm.models.requirements import Requirement, parse_requirement, strip_extras
from pdm.models.specifiers import get_specifier
from pdm.project import Project
from pdm.resolver import resolve
from pdm.utils import cd, normalize_name


def do_lock(
    project: Project,
    strategy: str = "all",
    tracked_names: Iterable[str] | None = None,
    requirements: list[Requirement] | None = None,
    dry_run: bool = False,
    refresh: bool = False,
    groups: list[str] | None = None,
    cross_platform: bool | None = None,
    hooks: HookManager | None = None,
) -> dict[str, Candidate]:
    """Performs the locking process and update lockfile."""
    hooks = hooks or HookManager(project)
    check_project_file(project)
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
                fetch_hashes(repo, mapping)
            lockfile = format_lockfile(project, mapping, dependencies)
        project.write_lockfile(lockfile, groups=groups)
        return mapping
    # TODO: multiple dependency definitions for the same package.
    if cross_platform is None:
        cross_platform = project.lockfile.cross_platform
    provider = project.get_provider(strategy, tracked_names, ignore_compatibility=cross_platform)
    if not requirements:
        requirements = [
            r for g, deps in project.all_dependencies.items() if groups is None or g in groups for r in deps.values()
        ]
    if not cross_platform:
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
            ui.echo(format_resolution_impossible(err), err=True)
            raise ResolutionImpossible("Unable to find a resolution") from None
        else:
            data = format_lockfile(project, mapping, dependencies)
            ui.echo(f"{termui.Emoji.LOCK} Lock successful")
            project.write_lockfile(data, write=not dry_run, groups=groups, cross_platform=cross_platform)
            hooks.try_emit("post_lock", resolution=mapping, dry_run=dry_run)

    return mapping


def resolve_candidates_from_lockfile(project: Project, requirements: Iterable[Requirement]) -> dict[str, Candidate]:
    ui = project.core.ui
    resolve_max_rounds = int(project.config["strategy.resolve_max_rounds"])
    reqs = [
        req for req in requirements if not req.marker or req.marker.evaluate(project.environment.marker_environment)
    ]
    with ui.logging("install-resolve"):
        with ui.open_spinner("Resolving packages from lockfile...") as spinner:
            reporter = BaseReporter()
            provider = project.get_provider(for_install=True)
            resolver: Resolver = project.core.resolver_class(provider, reporter)
            mapping, *_ = resolve(
                resolver,
                reqs,
                project.environment.python_requires,
                resolve_max_rounds,
            )
            spinner.update("Fetching hashes for resolved packages...")
            fetch_hashes(provider.repository, mapping)
    return mapping


def check_lockfile(project: Project, raise_not_exist: bool = True) -> str | None:
    """Check if the lock file exists and is up to date. Return the update strategy."""
    if not project.lockfile.exists():
        if raise_not_exist:
            raise ProjectError("Lock file does not exist, nothing to install")
        project.core.ui.echo("Lock file does not exist", style="warning", err=True)
        return "all"
    elif not project.lockfile.is_compatible():
        project.core.ui.echo(
            "Lock file version is not compatible with PDM, installation may fail",
            style="warning",
            err=True,
        )
        return "reuse"  # try to reuse the lockfile if possible
    elif not project.is_lockfile_hash_match():
        project.core.ui.echo(
            "Lock file hash doesn't match pyproject.toml, packages may be outdated",
            style="warning",
            err=True,
        )
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
        install_self=not no_self and "default" in selection and bool(project.name),
        reinstall=reinstall,
        only_keep=only_keep,
        fail_fast=fail_fast,
    )
    with project.core.ui.logging("install"):
        hooks.try_emit("pre_install", candidates=candidates, dry_run=dry_run)
        synchronizer.synchronize()
        hooks.try_emit("post_install", candidates=candidates, dry_run=dry_run)


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
    prerelease: bool = False,
    fail_fast: bool = False,
    hooks: HookManager | None = None,
) -> None:
    """Add packages and install"""
    hooks = hooks or HookManager(project)
    check_project_file(project)
    if editables and no_editable:
        raise PdmUsageError("Cannot use --no-editable with editable packages given.")
    group = selection.one()
    tracked_names: set[str] = set()
    requirements: dict[str, Requirement] = {}
    lock_groups = [] if project.lockfile.empty() else project.lockfile.groups
    if lock_groups is not None and group not in lock_groups:
        project.core.ui.echo(f"Adding group [success]{group}[/] to lockfile", err=True, style="info")
        lock_groups.append(group)
    if group == "default" or not selection.dev and group not in project.pyproject.settings.get("dev-dependencies", {}):
        if editables:
            raise PdmUsageError("Cannot add editables to the default or optional dependency group")
    for r in [parse_requirement(line, True) for line in editables] + [parse_requirement(line) for line in packages]:
        if project.name and normalize_name(project.name) == r.key and not r.extras:
            project.core.ui.echo(
                f"Package [req]{project.name}[/] is the project itself.",
                err=True,
                style="warning",
            )
            continue
        if r.is_file_or_url:
            r.relocate(project.backend)  # type: ignore[attr-defined]
        key = r.identify()
        r.prerelease = prerelease
        tracked_names.add(key)
        requirements[key] = r
    if requirements:
        project.core.ui.echo(
            f"Adding packages to [primary]{group}[/] "
            f"{'dev-' if selection.dev else ''}dependencies: "
            + ", ".join(f"[req]{r.as_line()}[/]" for r in requirements.values())
        )
    all_dependencies = project.all_dependencies
    group_deps = all_dependencies.setdefault(group, {})
    if unconstrained:
        if not requirements:
            raise PdmUsageError("--unconstrained requires at least one package")
        for req in group_deps.values():
            req.specifier = get_specifier("")
    group_deps.update(requirements)
    reqs = [r for g, deps in all_dependencies.items() if lock_groups is None or g in lock_groups for r in deps.values()]
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
    save_version_specifiers({group: deps_to_update}, resolved, save)
    if not dry_run:
        project.add_dependencies(deps_to_update, group, selection.dev or False)
        project.write_lockfile(project.lockfile._data, False, groups=lock_groups)
        hooks.try_emit("post_lock", resolution=resolved, dry_run=dry_run)
    _populate_requirement_names(group_deps)
    if sync:
        do_sync(
            project,
            selection=GroupSelection(project, groups=[group], default=False),
            no_editable=no_editable and tracked_names,
            no_self=no_self,
            requirements=list(group_deps.values()),
            dry_run=dry_run,
            fail_fast=fail_fast,
            hooks=hooks,
        )


def _populate_requirement_names(req_mapping: dict[str, Requirement]) -> None:
    # Update the requirement key if the name changed.
    for key, req in list(req_mapping.items()):
        if key and key.startswith(":empty:"):
            req_mapping[req.identify()] = req
            del req_mapping[key]


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
    hooks = hooks or HookManager(project)
    check_project_file(project)
    if len(packages) > 0 and (top or len(selection.groups) > 1 or not selection.default):
        raise PdmUsageError("packages argument can't be used together with multiple -G or " "--no-default or --top.")
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
    resolved = do_lock(
        project,
        strategy,
        chain.from_iterable(updated_deps.values()),
        reqs,
        dry_run=True,
        hooks=hooks,
        groups=locked_groups,
    )
    for deps in updated_deps.values():
        _populate_requirement_names(deps)
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
    hooks = hooks or HookManager(project)
    check_project_file(project)
    if not packages:
        raise PdmUsageError("Must specify at least one package to remove.")
    group = selection.one()
    lock_groups = project.lockfile.groups

    deps, _ = project.get_pyproject_dependencies(group, selection.dev or False)
    project.core.ui.echo(
        f"Removing packages from [primary]{group}[/] "
        f"{'dev-' if selection.dev else ''}dependencies: " + ", ".join(f"[req]{name}[/]" for name in packages)
    )
    with cd(project.root):
        for name in packages:
            req = parse_requirement(name)
            matched_indexes = sorted((i for i, r in enumerate(deps) if req.matches(r)), reverse=True)
            if not matched_indexes:
                raise ProjectError(f"[req]{name}[/] does not exist in [primary]{group}[/] dependencies.")
            for i in matched_indexes:
                del deps[i]
    cast(Array, deps).multiline(True)

    if not dry_run:
        project.pyproject.write()
    if lock_groups and group not in lock_groups:
        project.core.ui.echo(f"Group [success]{group}[/] isn't in lockfile, skipping lock.", style="warning", err=True)
        return
    do_lock(project, "reuse", dry_run=dry_run, hooks=hooks, groups=lock_groups)
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


def do_use(
    project: Project,
    python: str = "",
    first: bool = False,
    ignore_remembered: bool = False,
    ignore_requires_python: bool = False,
    save: bool = True,
    venv: str | None = None,
    hooks: HookManager | None = None,
) -> PythonInfo:
    """Use the specified python version and save in project config.
    The python can be a version string or interpreter path.
    """
    from pdm.cli.commands.venv.utils import get_venv_with_name
    from pdm.models.caches import JSONFileCache

    def version_matcher(py_version: PythonInfo) -> bool:
        return py_version.valid and (
            ignore_requires_python or project.python_requires.contains(str(py_version.version), True)
        )

    hooks = hooks or HookManager(project)

    selected_python: PythonInfo | None = None
    if venv:
        virtualenv = get_venv_with_name(project, venv)
        selected_python = PythonInfo.from_path(virtualenv.interpreter)

    if not project.cache_dir.exists():
        project.cache_dir.mkdir(parents=True)
    use_cache: JSONFileCache[str, str] = JSONFileCache(project.cache_dir / "use_cache.json")
    if python:
        python = python.strip()
    if selected_python is None and python and not ignore_remembered:
        if python in use_cache:
            path = use_cache.get(python)
            cached_python = PythonInfo.from_path(path)
            if not cached_python.valid:
                project.core.ui.echo(
                    f"The last selection is corrupted. {path!r}",
                    style="error",
                    err=True,
                )
            elif version_matcher(cached_python):
                project.core.ui.echo(
                    "Using the last selection, add '-i' to ignore it.",
                    style="warning",
                    err=True,
                )
                selected_python = cached_python

    if selected_python is None:
        found_interpreters = list(dict.fromkeys(project.find_interpreters(python)))
        matching_interpreters = list(filter(version_matcher, found_interpreters))
        if not found_interpreters:
            raise NoPythonVersion(f"No Python interpreter matching [success]{python}[/] is found.")
        if not matching_interpreters:
            project.core.ui.echo("Interpreters found but not matching:", err=True)
            for py in found_interpreters:
                info = py.identifier if py.valid else "Invalid"
                project.core.ui.echo(f"  - {py.path} ({info})", err=True)
            raise NoPythonVersion(
                f"No python is found meeting the requirement [success]python {project.python_requires!s}[/]"
            )
        if first or len(matching_interpreters) == 1:
            selected_python = matching_interpreters[0]
        else:
            project.core.ui.echo("Please enter the Python interpreter to use")
            for i, py_version in enumerate(matching_interpreters):
                project.core.ui.echo(f"{i}. [success]{py_version.path!s}[/] ({py_version.identifier})")
            selection = termui.ask(
                "Please select",
                default="0",
                prompt_type=int,
                choices=[str(i) for i in range(len(matching_interpreters))],
                show_choices=False,
            )
            selected_python = matching_interpreters[int(selection)]
        if python:
            use_cache.set(python, selected_python.path.as_posix())

    if not save:
        return selected_python
    saved_python = project._saved_python
    old_python = PythonInfo.from_path(saved_python) if saved_python else None
    project.core.ui.echo(
        f"Using Python interpreter: [success]{selected_python.path!s}[/] ({selected_python.identifier})"
    )
    project.python = selected_python
    if project.environment.is_local:
        project.core.ui.echo(
            "Using __pypackages__ because non-venv Python is used.",
            style="primary",
            err=True,
        )
    if (
        old_python
        and old_python.executable != selected_python.executable
        and isinstance(project.environment, PythonLocalEnvironment)
    ):
        project.core.ui.echo("Updating executable scripts...", style="primary")
        project.environment.update_shebangs(selected_python.executable.as_posix())
    hooks.try_emit("post_use", python=selected_python)
    return selected_python


def do_import(
    project: Project,
    filename: str,
    format: str | None = None,
    options: Namespace | None = None,
) -> None:
    """Import project metadata from given file.

    :param project: the project instance
    :param filename: the file name
    :param format: the file format, or guess if not given.
    :param options: other options parsed to the CLI.
    """
    from pdm.formats import FORMATS

    if not format:
        for key in FORMATS:
            if FORMATS[key].check_fingerprint(project, filename):
                break
        else:
            raise PdmUsageError(
                "Can't derive the file format automatically, please specify it via '-f/--format' option."
            )
    else:
        key = format
    if options is None:
        options = Namespace(dev=False, group=None)
    project_data, settings = FORMATS[key].convert(project, filename, options)
    pyproject = project.pyproject._data

    if "tool" not in pyproject or "pdm" not in pyproject["tool"]:
        pyproject.setdefault("tool", {})["pdm"] = tomlkit.table()
    if "build" in pyproject["tool"]["pdm"] and isinstance(pyproject["tool"]["pdm"]["build"], str):
        pyproject["tool"]["pdm"]["build"] = {
            "setup-script": pyproject["tool"]["pdm"]["build"],
            "run-setuptools": True,
        }
    if "project" not in pyproject:
        pyproject.add("project", tomlkit.table())
        pyproject["project"].add(tomlkit.comment("PEP 621 project metadata"))
        pyproject["project"].add(tomlkit.comment("See https://www.python.org/dev/peps/pep-0621/"))

    merge_dictionary(pyproject["project"], project_data)
    merge_dictionary(pyproject["tool"]["pdm"], settings)
    pyproject.setdefault("build-system", DEFAULT_BACKEND.build_system())

    if "requires-python" not in pyproject["project"]:
        python_version = f"{project.python.major}.{project.python.minor}"
        pyproject["project"]["requires-python"] = f">={python_version}"
        project.core.ui.echo(
            "The project's [primary]requires-python[/] has been set to [primary]>="
            f"{python_version}[/]. You can change it later if necessary."
        )
    project.pyproject.write()


def ask_for_import(project: Project) -> None:
    """Show possible importable files and ask user to decide"""
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
    do_import(project, str(filepath), key)


def print_pep582_command(project: Project, shell: str = "AUTO") -> None:
    """Print the export PYTHONPATH line to be evaluated by the shell."""
    import shellingham

    pep582_path = get_pep582_path(project)
    ui = project.core.ui

    if os.name == "nt":
        try:
            set_env_in_reg("PYTHONPATH", pep582_path)
        except PermissionError:
            ui.echo(
                "Permission denied, please run the terminal as administrator.",
                style="error",
                err=True,
            )
        ui.echo(
            "The environment variable has been saved, please restart the session to take effect.",
            style="success",
        )
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


def check_update(project: Project) -> None:
    """Check if there is a new version of PDM available"""
    from packaging.version import Version

    from pdm.cli.utils import is_homebrew_installation, is_pipx_installation, is_scoop_installation

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
        f"\nPDM [primary]{this_version}[/]",
        f" is installed, while [primary]{latest_version}[/]",
        " is available.\n",
        f"Please run [req]`{install_command}`[/]",
        " to upgrade.\n",
        f"Run [req]`{disable_command}`[/]",
        " to disable the check.",
    ]
    project.core.ui.echo("".join(message), err=True, style="info")
