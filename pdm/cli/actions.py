from __future__ import annotations

import contextlib
import datetime
import hashlib
import json
import os
import shutil
import sys
import textwrap
from argparse import Namespace
from collections import defaultdict
from itertools import chain
from typing import Collection, Iterable, Mapping, Sequence, cast

import tomlkit
from resolvelib.reporters import BaseReporter
from resolvelib.resolvers import ResolutionImpossible, ResolutionTooDeep, Resolver
from tomlkit.items import Array

from pdm import termui
from pdm.cli.hooks import HookManager
from pdm.cli.utils import (
    check_project_file,
    fetch_hashes,
    find_importable_files,
    format_lockfile,
    format_resolution_impossible,
    get_dist_location,
    merge_dictionary,
    save_version_specifiers,
    set_env_in_reg,
    translate_groups,
)
from pdm.exceptions import (
    InvalidPyVersion,
    NoPythonVersion,
    PdmUsageError,
    ProjectError,
)
from pdm.formats import FORMATS
from pdm.formats.base import array_of_inline_tables, make_array, make_inline_table
from pdm.models.caches import JSONFileCache
from pdm.models.candidates import Candidate
from pdm.models.python import PythonInfo
from pdm.models.requirements import Requirement, parse_requirement, strip_extras
from pdm.models.specifiers import get_specifier
from pdm.project import Project
from pdm.resolver import resolve
from pdm.utils import normalize_name

PEP582_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pep582")


def do_lock(
    project: Project,
    strategy: str = "all",
    tracked_names: Iterable[str] | None = None,
    requirements: list[Requirement] | None = None,
    dry_run: bool = False,
    refresh: bool = False,
    hooks: HookManager | None = None,
) -> dict[str, Candidate]:
    """Performs the locking process and update lockfile."""
    hooks = hooks or HookManager(project)
    check_project_file(project)
    if refresh:
        locked_repo = project.locked_repository
        repo = project.get_repository()
        mapping: dict[str, Candidate] = {}
        dependencies: dict[str, list[Requirement]] = {}
        with project.core.ui.open_spinner("Re-calculating hashes..."):
            for key, candidate in locked_repo.packages.items():
                reqs, python_requires, summary = locked_repo.candidate_info[key]
                candidate.summary = summary
                candidate.requires_python = python_requires
                ident = cast(str, key[0])
                mapping[ident] = candidate
                dependencies[ident] = list(map(parse_requirement, reqs))
            fetch_hashes(repo, mapping)
            lockfile = format_lockfile(project, mapping, dependencies)
        project.write_lockfile(lockfile)
        return mapping
    # TODO: multiple dependency definitions for the same package.
    provider = project.get_provider(strategy, tracked_names)
    if not requirements:
        requirements = [
            r for deps in project.all_dependencies.values() for r in deps.values()
        ]
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
                fetch_hashes(provider.repository, mapping)
        except ResolutionTooDeep:
            ui.echo(f"{termui.Emoji.LOCK} Lock failed", err=True)
            ui.echo(
                "The dependency resolution exceeds the maximum loop depth of "
                f"{resolve_max_rounds}, there may be some circular dependencies "
                "in your project. Try to solve them or increase the "
                f"[green]`strategy.resolve_max_rounds`[/] config.",
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
            project.write_lockfile(data, write=not dry_run)
            hooks.try_emit("post_lock", resolution=mapping, dry_run=dry_run)

    return mapping


def resolve_candidates_from_lockfile(
    project: Project, requirements: Iterable[Requirement]
) -> dict[str, Candidate]:
    ui = project.core.ui
    resolve_max_rounds = int(project.config["strategy.resolve_max_rounds"])
    reqs = [
        req
        for req in requirements
        if not req.marker or req.marker.evaluate(project.environment.marker_environment)
    ]
    with ui.logging("install-resolve"):
        with ui.open_spinner("Resolving packages from lockfile..."):
            reporter = BaseReporter()
            provider = project.get_provider(for_install=True)
            resolver: Resolver = project.core.resolver_class(provider, reporter)
            mapping, *_ = resolve(
                resolver,
                reqs,
                project.environment.python_requires,
                resolve_max_rounds,
            )
            fetch_hashes(provider.repository, mapping)
    return mapping


def check_lockfile(project: Project, raise_not_exist: bool = True) -> str | None:
    """Check if the lock file exists and is up to date. Return the update strategy."""
    if not project.lockfile_file.exists():
        if raise_not_exist:
            raise ProjectError("Lock file does not exist, nothing to install")
        project.core.ui.echo("Lock file does not exist", style="yellow", err=True)
        return "all"
    elif not project.is_lockfile_compatible():
        project.core.ui.echo(
            "Lock file version is not compatible with PDM, installation may fail",
            style="yellow",
            err=True,
        )
        return "all"
    elif not project.is_lockfile_hash_match():
        project.core.ui.echo(
            "Lock file hash doesn't match pyproject.toml, packages may be outdated",
            style="yellow",
            err=True,
        )
        return "reuse"
    return None


def do_sync(
    project: Project,
    *,
    groups: Collection[str] = (),
    dev: bool = True,
    default: bool = True,
    dry_run: bool = False,
    clean: bool = False,
    requirements: list[Requirement] | None = None,
    tracked_names: Collection[str] | None = None,
    no_editable: bool | Collection[str] = False,
    no_self: bool = False,
    reinstall: bool = False,
    only_keep: bool = False,
    hooks: HookManager | None = None,
) -> None:
    """Synchronize project"""
    hooks = hooks or HookManager(project)
    if requirements is None:
        groups = translate_groups(project, default, dev, groups or ())
        requirements = []
        for group in groups:
            requirements.extend(project.get_dependencies(group).values())
    candidates = resolve_candidates_from_lockfile(project, requirements)
    if tracked_names and dry_run:
        candidates = {
            name: c for name, c in candidates.items() if name in tracked_names
        }
    handler = project.core.synchronizer_class(
        candidates,
        project.environment,
        clean,
        dry_run,
        no_editable=no_editable,
        install_self=not no_self and "default" in groups and bool(project.name),
        use_install_cache=project.config["install.cache"],
        reinstall=reinstall,
        only_keep=only_keep,
    )
    hooks.try_emit("pre_install", candidates=candidates, dry_run=dry_run)
    handler.synchronize()
    hooks.try_emit("post_install", candidates=candidates, dry_run=dry_run)


def do_add(
    project: Project,
    dev: bool = False,
    group: str | None = None,
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
    hooks: HookManager | None = None,
) -> None:
    """Add packages and install"""
    hooks = hooks or HookManager(project)
    check_project_file(project)
    if not editables and not packages:
        raise PdmUsageError("Must specify at least one package or editable package.")
    if editables and no_editable:
        raise PdmUsageError("Cannot use --no-editable with editable packages given.")
    if not group:
        group = "dev" if dev else "default"
    tracked_names: set[str] = set()
    requirements: dict[str, Requirement] = {}
    if (
        group == "default"
        or not dev
        and group not in project.tool_settings.get("dev-dependencies", {})
    ):
        if editables:
            raise PdmUsageError(
                "Cannot add editables to the default or optional dependency group"
            )
    for r in [parse_requirement(line, True) for line in editables] + [
        parse_requirement(line) for line in packages
    ]:
        key = r.identify()
        r.prerelease = prerelease
        tracked_names.add(key)
        requirements[key] = r
    project.core.ui.echo(
        f"Adding packages to {group} {'dev-' if dev else ''}dependencies: "
        + ", ".join(f"[bold green]{r.as_line()}[/]" for r in requirements.values())
    )
    all_dependencies = project.all_dependencies
    group_deps = all_dependencies.setdefault(group, {})
    if unconstrained:
        for req in group_deps.values():
            req.specifier = get_specifier("")
    group_deps.update(requirements)
    reqs = [r for deps in all_dependencies.values() for r in deps.values()]
    resolved = do_lock(
        project, strategy, tracked_names, reqs, dry_run=dry_run, hooks=hooks
    )

    # Update dependency specifiers and lockfile hash.
    deps_to_update = group_deps if unconstrained else requirements
    save_version_specifiers({group: deps_to_update}, resolved, save)
    if not dry_run:
        project.add_dependencies(deps_to_update, group, dev)
        project.write_lockfile(project.lockfile, False)

    if sync:
        do_sync(
            project,
            groups=(group,),
            default=False,
            no_editable=no_editable and tracked_names,
            no_self=no_self,
            requirements=list(group_deps.values()),
            dry_run=dry_run,
            hooks=hooks,
        )


def do_update(
    project: Project,
    *,
    dev: bool | None = None,
    groups: Sequence[str] = (),
    default: bool = True,
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
    hooks: HookManager | None = None,
) -> None:
    """Update specified packages or all packages"""
    hooks = hooks or HookManager(project)
    check_project_file(project)
    if len(packages) > 0 and (top or len(groups) > 1 or not default):
        raise PdmUsageError(
            "packages argument can't be used together with multiple -G or "
            "--no-default and --top."
        )
    all_dependencies = project.all_dependencies
    updated_deps: dict[str, dict[str, Requirement]] = defaultdict(dict)
    install_dev = True if dev is None else dev
    if not packages:
        if prerelease:
            raise PdmUsageError("--prerelease must be used with packages given")
        groups = translate_groups(project, default, install_dev, groups or ())
        for group in groups:
            updated_deps[group] = all_dependencies[group]
    else:
        group = groups[0] if groups else ("dev" if dev else "default")
        dependencies = all_dependencies[group]
        for name in packages:
            matched_name = next(
                (
                    k
                    for k in dependencies
                    if normalize_name(strip_extras(k)[0]) == normalize_name(name)
                ),
                None,
            )
            if not matched_name:
                raise ProjectError(
                    f"[bold green]{name}[/] does not exist in {group} "
                    f"{'dev-' if dev else ''}dependencies."
                )
            dependencies[matched_name].prerelease = prerelease
            updated_deps[group][matched_name] = dependencies[matched_name]
        project.core.ui.echo(
            "Updating packages: {}.".format(
                ", ".join(
                    f"[bold green]{v}[/]"
                    for v in chain.from_iterable(updated_deps.values())
                )
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
        dry_run=dry_run,
        hooks=hooks,
    )
    if sync or dry_run:
        do_sync(
            project,
            groups=groups,
            dev=install_dev,
            default=default,
            clean=False,
            dry_run=dry_run,
            requirements=[r for deps in updated_deps.values() for r in deps.values()],
            tracked_names=list(chain.from_iterable(updated_deps.values()))
            if top
            else None,
            no_editable=no_editable,
            no_self=no_self,
            hooks=hooks,
        )
    if unconstrained and not dry_run:
        # Need to update version constraints
        save_version_specifiers(updated_deps, resolved, save)
        for group, deps in updated_deps.items():
            project.add_dependencies(deps, group, dev or False)
        lockfile = project.lockfile
        project.write_lockfile(lockfile, False)


def do_remove(
    project: Project,
    dev: bool = False,
    group: str | None = None,
    sync: bool = True,
    packages: Collection[str] = (),
    no_editable: bool = False,
    no_self: bool = False,
    dry_run: bool = False,
    hooks: HookManager | None = None,
) -> None:
    """Remove packages from working set and pyproject.toml"""
    hooks = hooks or HookManager(project)
    check_project_file(project)
    if not packages:
        raise PdmUsageError("Must specify at least one package to remove.")
    if not group:
        group = "dev" if dev else "default"
    if group not in list(project.iter_groups()):
        raise ProjectError(f"No-exist group {group}")

    deps = project.get_pyproject_dependencies(group, dev)
    project.core.ui.echo(
        f"Removing packages from {group} {'dev-' if dev else ''}dependencies: "
        + ", ".join(f"[bold green]{name}[/]" for name in packages)
    )
    for name in packages:
        req = parse_requirement(name)
        matched_indexes = sorted(
            (i for i, r in enumerate(deps) if req.matches(r)), reverse=True
        )
        if not matched_indexes:
            raise ProjectError(
                f"[bold green]{name}[/] does not exist in {group} dependencies."
            )
        for i in matched_indexes:
            del deps[i]
    cast(Array, deps).multiline(True)

    if not dry_run:
        project.write_pyproject()
    do_lock(project, "reuse", dry_run=dry_run, hooks=hooks)
    if sync:
        do_sync(
            project,
            groups=(group,),
            default=False,
            clean=True,
            no_editable=no_editable,
            no_self=no_self,
            dry_run=dry_run,
            hooks=hooks,
        )


def do_list(
    project: Project,
    graph: bool = False,
    reverse: bool = False,
    freeze: bool = False,
    json: bool = False,
) -> None:
    """Display a list of packages installed in the local packages directory."""
    from pdm.cli.utils import build_dependency_graph, show_dependency_graph

    check_project_file(project)
    working_set = project.environment.get_working_set()
    if graph:
        dep_graph = build_dependency_graph(
            working_set, project.environment.marker_environment
        )
        show_dependency_graph(project, dep_graph, reverse=reverse, json=json)
    else:
        if reverse:
            raise PdmUsageError("--reverse must be used with --graph")
        if json:
            raise PdmUsageError("--json must be used with --graph")
        if freeze:
            reqs = sorted(
                (
                    Requirement.from_dist(dist)
                    .as_line()
                    .replace(
                        "${PROJECT_ROOT}",
                        project.root.absolute().as_posix().lstrip("/"),
                    )
                    for dist in sorted(
                        working_set.values(), key=lambda d: d.metadata["Name"]
                    )
                ),
                key=lambda x: x.lower(),
            )
            project.core.ui.echo("\n".join(reqs))
            return
        rows = [
            (f"[b green]{k}[/]", f"[yellow]{v.version}[/]", get_dist_location(v))
            for k, v in sorted(working_set.items())
        ]
        project.core.ui.display_columns(rows, ["Package", "Version", "Location"])


def do_build(
    project: Project,
    sdist: bool = True,
    wheel: bool = True,
    dest: str = "dist",
    clean: bool = True,
    config_settings: Mapping[str, str] | None = None,
    hooks: HookManager | None = None,
) -> None:
    """Build artifacts for distribution."""
    from pdm.builders import SdistBuilder, WheelBuilder

    hooks = hooks or HookManager(project)

    if project.is_global:
        raise ProjectError("Not allowed to build based on the global project.")
    if not wheel and not sdist:
        project.core.ui.echo("All artifacts are disabled, nothing to do.", err=True)
        return
    if not os.path.isabs(dest):
        dest = project.root.joinpath(dest).as_posix()
    if clean:
        shutil.rmtree(dest, ignore_errors=True)
    hooks.try_emit("pre_build", dest=dest, config_settings=config_settings)
    artifacts: list[str] = []
    with project.core.ui.logging("build"):
        if sdist:
            project.core.ui.echo("Building sdist...")
            loc = SdistBuilder(project.root, project.environment).build(
                dest, config_settings
            )
            project.core.ui.echo(f"Built sdist at {loc}")
            artifacts.append(loc)
        if wheel:
            project.core.ui.echo("Building wheel...")
            loc = WheelBuilder(project.root, project.environment).build(
                dest, config_settings
            )
            project.core.ui.echo(f"Built wheel at {loc}")
            artifacts.append(loc)
    hooks.try_emit("post_build", artifacts=artifacts, config_settings=config_settings)


def do_init(
    project: Project,
    name: str = "",
    version: str = "",
    description: str = "",
    license: str = "MIT",
    author: str = "",
    email: str = "",
    python_requires: str = "",
    hooks: HookManager | None = None,
) -> None:
    """Bootstrap the project and create a pyproject.toml"""
    hooks = hooks or HookManager(project)
    data = {
        "project": {
            "name": name,
            "version": version,
            "description": description,
            "authors": array_of_inline_tables([{"name": author, "email": email}]),
            "license": make_inline_table({"text": license}),
            "dependencies": make_array([], True),
        },
        "build-system": {
            "requires": ["pdm-pep517>=1.0.0"],
            "build-backend": "pdm.pep517.api",
        },
    }
    if python_requires and python_requires != "*":
        data["project"]["requires-python"] = python_requires  # type: ignore
    if name and version:
        readme = next(project.root.glob("README*"), None)
        if readme is None:
            readme = project.root.joinpath("README.md")
            readme.write_text(f"# {name}\n\n{description}\n")
        data["project"]["readme"] = readme.name  # type: ignore
    get_specifier(python_requires)
    if not project.pyproject:
        project._pyproject = data
    else:
        project._pyproject["project"] = data["project"]  # type: ignore
        project._pyproject["build-system"] = data["build-system"]  # type: ignore
    project.write_pyproject()
    hooks.try_emit("post_init")


def do_use(
    project: Project,
    python: str = "",
    first: bool = False,
    ignore_remembered: bool = False,
    ignore_requires_python: bool = False,
    hooks: HookManager | None = None,
) -> PythonInfo:
    """Use the specified python version and save in project config.
    The python can be a version string or interpreter path.
    """
    hooks = hooks or HookManager(project)

    if python:
        python = python.strip()

    def version_matcher(py_version: PythonInfo) -> bool:
        return ignore_requires_python or project.python_requires.contains(
            str(py_version.version), True
        )

    if not project.cache_dir.exists():
        project.cache_dir.mkdir(parents=True)
    use_cache: JSONFileCache[str, str] = JSONFileCache(
        project.cache_dir / "use_cache.json"
    )
    selected_python: PythonInfo | None = None
    if python and not ignore_remembered:
        if python in use_cache:
            path = use_cache.get(python)
            cached_python = PythonInfo.from_path(path)
            if not cached_python.valid:
                project.core.ui.echo(
                    f"The last selection is corrupted. {path!r}",
                    style="red",
                    err=True,
                )
            elif version_matcher(cached_python):
                project.core.ui.echo(
                    "Using the last selection, add '-i' to ignore it.",
                    style="yellow",
                    err=True,
                )
                selected_python = cached_python

    if selected_python is None:
        found_interpreters = list(dict.fromkeys(project.find_interpreters(python)))
        matching_interpreters = list(filter(version_matcher, found_interpreters))
        if not found_interpreters:
            raise NoPythonVersion(
                f"No Python interpreter matching [green]{python}[/] is found."
            )
        if not matching_interpreters:
            project.core.ui.echo("Interpreters found but not matching:", err=True)
            for py in found_interpreters:
                project.core.ui.echo(f"  - {py.executable} ({py.identifier})", err=True)
            raise NoPythonVersion(
                "No python is found meeting the requirement "
                f"[green]python {str(project.python_requires)}[/]"
            )
        if first or len(matching_interpreters) == 1:
            selected_python = matching_interpreters[0]
        else:
            project.core.ui.echo("Please enter the Python interpreter to use")
            for i, py_version in enumerate(matching_interpreters):
                project.core.ui.echo(
                    f"{i}. [green]{str(py_version.executable)}[/] "
                    f"({py_version.identifier})"
                )
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

    if not selected_python.valid:
        path = str(selected_python.executable)
        raise InvalidPyVersion(f"Invalid Python interpreter: {path}")

    old_python = project.python if "python.path" in project.config else None
    project.core.ui.echo(
        "Using Python interpreter: "
        f"[green]{str(selected_python.executable)}[/] "
        f"({selected_python.identifier})"
    )
    project.python = selected_python
    if (
        old_python
        and old_python.path != selected_python.path
        and not project.environment.is_global
    ):
        project.core.ui.echo("Updating executable scripts...", style="cyan")
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
    if not format:
        for key in FORMATS:
            if FORMATS[key].check_fingerprint(project, filename):
                break
        else:
            raise PdmUsageError(
                "Can't derive the file format automatically, "
                "please specify it via '-f/--format' option."
            )
    else:
        key = format
    if options is None:
        options = Namespace(dev=False, group=None)
    project_data, settings = FORMATS[key].convert(project, filename, options)
    pyproject = project.pyproject or tomlkit.document()

    if "tool" not in pyproject or "pdm" not in pyproject["tool"]:  # type: ignore
        pyproject.setdefault("tool", {})["pdm"] = tomlkit.table()
    if "build" in pyproject["tool"]["pdm"] and isinstance(
        pyproject["tool"]["pdm"]["build"], str
    ):
        pyproject["tool"]["pdm"]["build"] = {
            "setup-script": pyproject["tool"]["pdm"]["build"],
            "run-setuptools": True,
        }
    if "project" not in pyproject:
        pyproject.add("project", tomlkit.table())  # type: ignore
        pyproject["project"].add(  # type: ignore
            tomlkit.comment("PEP 621 project metadata")
        )
        pyproject["project"].add(  # type: ignore
            tomlkit.comment("See https://www.python.org/dev/peps/pep-0621/")
        )

    merge_dictionary(pyproject["project"], project_data)  # type: ignore
    merge_dictionary(pyproject["tool"]["pdm"], settings)  # type: ignore
    pyproject["build-system"] = {
        "requires": ["pdm-pep517>=1.0.0"],
        "build-backend": "pdm.pep517.api",
    }
    project.pyproject = cast(dict, pyproject)
    project.write_pyproject()


def ask_for_import(project: Project) -> None:
    """Show possible importable files and ask user to decide"""
    importable_files = list(find_importable_files(project))
    if not importable_files:
        return
    project.core.ui.echo(
        "Found following files from other formats that you may import:", style="cyan"
    )
    for i, (key, filepath) in enumerate(importable_files):
        project.core.ui.echo(f"{i}. [green]{filepath.as_posix()}[/] ({key})")
    project.core.ui.echo(
        f"{len(importable_files)}. [yellow]don't do anything, I will import later.[/]"
    )
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


def print_pep582_command(ui: termui.UI, shell: str = "AUTO") -> None:
    """Print the export PYTHONPATH line to be evaluated by the shell."""
    import shellingham

    if os.name == "nt":
        try:
            set_env_in_reg("PYTHONPATH", PEP582_PATH)
        except PermissionError:
            ui.echo(
                "Permission denied, please run the terminal as administrator.",
                style="red",
                err=True,
            )
        ui.echo(
            "The environment variable has been saved, "
            "please restart the session to take effect.",
            style="green",
        )
        return
    lib_path = PEP582_PATH.replace("'", "\\'")
    if shell == "AUTO":
        shell = shellingham.detect_shell()[0]
    shell = shell.lower()
    if shell in ("zsh", "bash"):
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
        result = textwrap.dedent(
            f"""
            if test -n "$PYTHONPATH"
                set -x PYTHONPATH '{lib_path}' $PYTHONPATH
            else
                set -x PYTHONPATH '{lib_path}'
            end
            """
        ).strip()
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
        raise PdmUsageError(
            f"Unsupported shell: {shell}, please specify another shell "
            "via `--pep582 <SHELL>`"
        )
    ui.echo(result)


def get_latest_version(project: Project) -> str | None:
    """Get the latest version of PDM from PyPI, cache for 7 days"""
    cache_key = hashlib.sha224(sys.executable.encode()).hexdigest()
    cache_file = project.cache("self-check") / cache_key
    state = {}
    with contextlib.suppress(OSError):
        state = json.loads(cache_file.read_text())
    current_time = datetime.datetime.utcnow().timestamp()
    if (
        state.get("last-check")
        and current_time - state["last-check"] < 60 * 60 * 24 * 7
    ):
        return cast(str, state["latest-version"])
    with project.environment.get_finder(
        [project.default_source], ignore_compatibility=True
    ) as finder:
        candidate = finder.find_best_match("pdm").best
    if not candidate:
        return None
    latest_version = str(candidate.version)
    state.update({"latest-version": latest_version, "last-check": current_time})
    with contextlib.suppress(OSError):
        cache_file.write_text(json.dumps(state))
    return latest_version


def check_update(project: Project) -> None:
    """Check if there is a new version of PDM available"""
    import sys
    from shlex import quote

    from packaging.version import parse as parse_version

    from pdm.cli.utils import (
        is_homebrew_installation,
        is_pipx_installation,
        is_scoop_installation,
    )

    this_version = project.core.version
    latest_version = get_latest_version(project)
    if latest_version is None or parse_version(this_version) >= parse_version(
        latest_version
    ):
        return
    if is_pipx_installation():  # pragma: no cover
        install_command = "pipx upgrade pdm"
    elif is_scoop_installation():  # pragma: no cover
        install_command = "scoop update pdm"
    elif is_homebrew_installation():  # pragma: no cover
        install_command = "brew upgrade pdm"
    else:
        install_command = f"{quote(sys.executable)} -m pip install -U pdm"

    disable_command = "pdm config check_update false"

    message = [
        f"\nPDM [cyan]{this_version}[/]",
        f" is installed, while [cyan]{latest_version}[/]",
        " is available.\n",
        f"Please run [bold green]`{install_command}`[/]",
        " to upgrade.\n",
        f"Run [bold green]`{disable_command}`[/]",
        " to disable the check.",
    ]
    project.core.ui.echo("".join(message), err=True, style="blue")
