from __future__ import annotations

import os
import shutil
import textwrap
from argparse import Namespace
from collections import defaultdict
from itertools import chain
from pathlib import Path
from typing import Iterable, Mapping, Sequence, cast

import atoml
import click
from resolvelib.reporters import BaseReporter
from resolvelib.resolvers import ResolutionImpossible, ResolutionTooDeep, Resolver

from pdm import termui
from pdm.cli.utils import (
    check_project_file,
    find_importable_files,
    format_lockfile,
    format_resolution_impossible,
    frozen_requirement_from_dist,
    get_dist_location,
    merge_dictionary,
    save_version_specifiers,
    set_env_in_reg,
    translate_groups,
)
from pdm.exceptions import NoPythonVersion, PdmUsageError, ProjectError
from pdm.formats import FORMATS
from pdm.formats.base import array_of_inline_tables, make_array, make_inline_table
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
) -> dict[str, Candidate]:
    """Performs the locking process and update lockfile."""
    check_project_file(project)
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
        with ui.open_spinner(title="Resolving dependencies", spinner="dots") as spin:
            reporter = project.get_reporter(requirements, tracked_names, spin)
            resolver: Resolver = project.core.resolver_class(provider, reporter)
            try:
                mapping, dependencies, summaries = resolve(
                    resolver,
                    requirements,
                    project.environment.python_requires,
                    resolve_max_rounds,
                )
            except ResolutionTooDeep:
                spin.fail(f"{termui.Emoji.LOCK} Lock failed")
                ui.echo(
                    "The dependency resolution exceeds the maximum loop depth of "
                    f"{resolve_max_rounds}, there may be some circular dependencies "
                    "in your project. Try to solve them or increase the "
                    f"{termui.green('`strategy.resolve_max_rounds`')} config.",
                    err=True,
                )
                raise
            except ResolutionImpossible as err:
                spin.fail(f"{termui.Emoji.LOCK} Lock failed")
                ui.echo(format_resolution_impossible(err), err=True)
                raise
            else:
                data = format_lockfile(mapping, dependencies, summaries)
                spin.succeed(f"{termui.Emoji.LOCK} Lock successful")

    project.write_lockfile(data, write=not dry_run)

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
    return mapping


def do_sync(
    project: Project,
    *,
    groups: Sequence[str] = (),
    dev: bool = True,
    default: bool = True,
    dry_run: bool = False,
    clean: bool = False,
    requirements: list[Requirement] | None = None,
    tracked_names: Sequence[str] | None = None,
    no_editable: bool = False,
    no_self: bool = False,
    reinstall: bool = False,
) -> None:
    """Synchronize project"""
    if requirements is None:
        if not project.lockfile_file.exists():
            raise ProjectError("Lock file does not exist, nothing to sync")
        elif not project.is_lockfile_compatible():
            project.core.ui.echo(
                "Lock file version is not compatible with PDM, "
                "install may fail, please regenerate the pdm.lock",
                err=True,
            )
        elif not project.is_lockfile_hash_match():
            project.core.ui.echo(
                "Lock file hash doesn't match pyproject.toml, packages may be outdated",
                err=True,
            )
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
        install_self=not no_self and "default" in groups and bool(project.meta.name),
        use_install_cache=project.config["feature.install_cache"],
        reinstall=reinstall,
    )
    handler.synchronize()


def do_add(
    project: Project,
    dev: bool = False,
    group: str | None = None,
    sync: bool = True,
    save: str = "compatible",
    strategy: str = "reuse",
    editables: Iterable[str] = (),
    packages: Iterable[str] = (),
    unconstrained: bool = False,
    no_editable: bool = False,
    no_self: bool = False,
) -> None:
    """Add packages and install"""
    check_project_file(project)
    if not editables and not packages:
        raise PdmUsageError("Must specify at least one package or editable package.")
    if not group:
        group = "dev" if dev else "default"
    tracked_names: set[str] = set()
    requirements: dict[str, Requirement] = {}
    for r in [parse_requirement(line, True) for line in editables] + [
        parse_requirement(line) for line in packages
    ]:
        key = r.identify()
        tracked_names.add(key)
        requirements[key] = r
    project.core.ui.echo(
        f"Adding packages to {group} {'dev-' if dev else ''}dependencies: "
        + ", ".join(termui.green(key or "", bold=True) for key in requirements)
    )
    all_dependencies = project.all_dependencies
    group_deps = all_dependencies.setdefault(group, {})
    if unconstrained:
        for req in group_deps.values():
            req.specifier = get_specifier("")
    group_deps.update(requirements)
    reqs = [r for deps in all_dependencies.values() for r in deps.values()]
    resolved = do_lock(project, strategy, tracked_names, reqs)

    # Update dependency specifiers and lockfile hash.
    deps_to_update = group_deps if unconstrained else requirements
    save_version_specifiers({group: deps_to_update}, resolved, save)
    project.add_dependencies(deps_to_update, group, dev)
    lockfile = project.lockfile
    project.write_lockfile(lockfile, False)

    if sync:
        do_sync(
            project,
            groups=(group,),
            default=False,
            no_editable=no_editable,
            no_self=no_self,
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
    packages: Sequence[str] = (),
    no_editable: bool = False,
    no_self: bool = False,
) -> None:
    """Update specified packages or all packages"""
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
        groups = translate_groups(project, default, install_dev, groups or ())
        for group in groups:
            updated_deps[group] = all_dependencies[group]
    else:
        group = groups[0] if groups else ("dev" if dev else "default")
        dependencies = all_dependencies[group]
        for name in packages:
            matched_name = next(
                filter(
                    lambda k: normalize_name(strip_extras(k)[0])
                    == normalize_name(name),
                    dependencies.keys(),
                ),
                None,
            )
            if not matched_name:
                raise ProjectError(
                    "{} does not exist in {} {}dependencies.".format(
                        termui.green(name, bold=True), group, "dev-" if dev else ""
                    )
                )
            updated_deps[group][matched_name] = dependencies[matched_name]
        project.core.ui.echo(
            "Updating packages: {}.".format(
                ", ".join(
                    termui.green(v, bold=True)
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
        strategy if top or packages else "all",
        chain.from_iterable(updated_deps.values()),
        reqs,
        dry_run=dry_run,
    )
    do_sync(
        project,
        groups=groups,
        dev=install_dev,
        default=default,
        clean=False,
        dry_run=dry_run,
        requirements=[r for deps in updated_deps.values() for r in deps.values()],
        tracked_names=list(chain.from_iterable(updated_deps.values())) if top else None,
        no_editable=no_editable,
        no_self=no_self,
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
    packages: Sequence[str] = (),
    no_editable: bool = False,
    no_self: bool = False,
) -> None:
    """Remove packages from working set and pyproject.toml"""
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
        + ", ".join(str(termui.green(name, bold=True)) for name in packages)
    )
    for name in packages:
        req = parse_requirement(name)
        matched_indexes = sorted(
            (i for i, r in enumerate(deps) if req.matches(r, False)), reverse=True
        )
        if not matched_indexes:
            raise ProjectError(
                "{} does not exist in {} dependencies.".format(
                    termui.green(name, bold=True), group
                )
            )
        for i in matched_indexes:
            del deps[i]

    project.write_pyproject()
    do_lock(project, "reuse")
    if sync:
        do_sync(
            project,
            groups=(group,),
            default=False,
            clean=True,
            no_editable=no_editable,
            no_self=no_self,
        )


def do_list(
    project: Project,
    graph: bool = False,
    reverse: bool = False,
    freeze: bool = False,
    json: bool = False,
) -> None:
    """Display a list of packages installed in the local packages directory."""
    from pdm.cli.utils import build_dependency_graph, format_dependency_graph

    check_project_file(project)
    working_set = project.environment.get_working_set()
    if graph:
        dep_graph = build_dependency_graph(
            working_set, project.environment.marker_environment
        )
        project.core.ui.echo(
            format_dependency_graph(project, dep_graph, reverse=reverse, json=json)
        )
    else:
        if reverse:
            raise PdmUsageError("--reverse must be used with --graph")
        if json:
            raise PdmUsageError("--json must be used with --graph")
        if freeze:
            reqs = [
                frozen_requirement_from_dist(dist)
                for dist in sorted(
                    working_set.values(), key=lambda d: d.metadata["Name"]
                )
            ]
            project.core.ui.echo("".join(reqs))
            return
        rows = [
            (termui.green(k, bold=True), termui.yellow(v.version), get_dist_location(v))
            for k, v in sorted(working_set.items())
        ]
        project.core.ui.display_columns(rows, ["Package", "Version", "Location"])


def do_build(
    project: Project,
    sdist: bool = True,
    wheel: bool = True,
    dest: str = "dist",
    clean: bool = True,
    isolated: bool = True,
    config_settings: Mapping[str, str] | None = None,
) -> None:
    """Build artifacts for distribution."""
    from pdm.builders import SdistBuilder, WheelBuilder

    if project.is_global:
        raise ProjectError("Not allowed to build based on the global project.")
    if not wheel and not sdist:
        project.core.ui.echo("All artifacts are disabled, nothing to do.", err=True)
        return
    if not os.path.isabs(dest):
        dest = project.root.joinpath(dest).as_posix()
    if clean:
        shutil.rmtree(dest, ignore_errors=True)
    with project.core.ui.logging("build"):
        if sdist:
            project.core.ui.echo("Building sdist...")
            loc = SdistBuilder(
                project.root, project.environment, isolated=isolated
            ).build(dest, config_settings)
            project.core.ui.echo(f"Built sdist at {loc}")
        if wheel:
            project.core.ui.echo("Building wheel...")
            loc = WheelBuilder(
                project.root, project.environment, isolated=isolated
            ).build(dest, config_settings)
            project.core.ui.echo(f"Built wheel at {loc}")


def do_init(
    project: Project,
    name: str = "",
    version: str = "",
    license: str = "MIT",
    author: str = "",
    email: str = "",
    python_requires: str = "",
) -> None:
    """Bootstrap the project and create a pyproject.toml"""
    data = {
        "project": {
            "name": name,
            "version": version,
            "description": "",
            "authors": array_of_inline_tables([{"name": author, "email": email}]),
            "license": make_inline_table({"text": license}),
            "urls": {"homepage": ""},
            "dependencies": make_array([], True),
            "requires-python": "" if python_requires == "*" else python_requires,
            "dynamic": ["classifiers"],
        },
        "build-system": {"requires": ["pdm-pep517"], "build-backend": "pdm.pep517.api"},
    }
    get_specifier(python_requires)
    if not project.pyproject:
        project._pyproject = data
    else:
        project._pyproject["project"] = data["project"]  # type: ignore
        project._pyproject["build-system"] = data["build-system"]  # type: ignore
    project.write_pyproject()


def do_use(project: Project, python: str = "", first: bool = False) -> None:
    """Use the specified python version and save in project config.
    The python can be a version string or interpreter path.
    """

    def version_matcher(py_version: PythonInfo) -> bool:
        return project.python_requires.contains(str(py_version.version))

    if python:
        python = python.strip()

    found_interpreters = list(
        dict.fromkeys(filter(version_matcher, project.find_interpreters(python)))
    )
    if not found_interpreters:
        raise NoPythonVersion("Python interpreter is not found on the system.")
    if first or len(found_interpreters) == 1:
        selected_python = found_interpreters[0]
    else:
        project.core.ui.echo("Please enter the Python interpreter to use")
        for i, py_version in enumerate(found_interpreters):
            project.core.ui.echo(
                f"{i}. {termui.green(py_version.executable)} ({py_version.identifier})"
            )
        selection = click.prompt(
            "Please select:",
            type=click.Choice([str(i) for i in range(len(found_interpreters))]),
            default="0",
            show_choices=False,
        )
        selected_python = found_interpreters[int(selection)]

    old_path = project.python.executable if "python.path" in project.config else None
    new_path = selected_python.executable
    project.core.ui.echo(
        "Using Python interpreter: {} ({})".format(
            termui.green(str(new_path)),
            selected_python.identifier,
        )
    )
    project.python = selected_python
    if (
        old_path
        and Path(old_path) != Path(new_path)
        and not project.environment.is_global
    ):
        project.core.ui.echo(termui.cyan("Updating executable scripts..."))
        project.environment.update_shebangs(old_path, new_path)


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
    pyproject = project.pyproject or atoml.document()

    if "tool" not in pyproject or "pdm" not in pyproject["tool"]:  # type: ignore
        pyproject.setdefault("tool", {})["pdm"] = atoml.table()

    if "project" not in pyproject:
        pyproject.add("project", atoml.table())  # type: ignore
        pyproject["project"].add(  # type: ignore
            atoml.comment("PEP 621 project metadata")
        )
        pyproject["project"].add(  # type: ignore
            atoml.comment("See https://www.python.org/dev/peps/pep-0621/")
        )

    merge_dictionary(pyproject["project"], project_data)  # type: ignore
    merge_dictionary(pyproject["tool"]["pdm"], settings)  # type: ignore
    pyproject["build-system"] = {
        "requires": ["pdm-pep517"],
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
        termui.cyan("Found following files from other formats that you may import:")
    )
    for i, (key, filepath) in enumerate(importable_files):
        project.core.ui.echo(f"{i}. {termui.green(filepath.as_posix())} ({key})")
    project.core.ui.echo(
        "{}. {}".format(
            len(importable_files),
            termui.yellow("don't do anything, I will import later."),
        )
    )
    choice = click.prompt(
        "Please select:",
        type=click.Choice([str(i) for i in range(len(importable_files) + 1)]),
        show_default=False,
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
                termui.red(
                    "Permission denied, please run the terminal as administrator."
                ),
                err=True,
            )
        ui.echo(
            termui.green(
                "The environment variable has been saved, "
                "please restart the session to take effect."
            )
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


def migrate_pyproject(project: Project) -> None:
    """Migrate the legacy pyproject format to PEP 621"""

    if project.pyproject and "project" in project.pyproject:
        pyproject = project.pyproject
        settings = {}
        updated_fields = []
        for field in ("includes", "excludes", "build", "package-dir"):
            if field in pyproject["project"]:
                updated_fields.append(field)
                settings[field] = pyproject["project"].pop(field)
        if "dev-dependencies" in pyproject["project"]:
            if pyproject["project"]["dev-dependencies"]:
                settings["dev-dependencies"] = {
                    "dev": pyproject["project"]["dev-dependencies"]
                }
            del pyproject["project"]["dev-dependencies"]
            updated_fields.append("dev-dependencies")
        if updated_fields:
            if "tool" not in pyproject or "pdm" not in pyproject["tool"]:
                pyproject.setdefault("tool", {})["pdm"] = atoml.table()
            pyproject["tool"]["pdm"].update(settings)
            project.pyproject = pyproject
            project.write_pyproject()
            project.core.ui.echo(
                f"{termui.yellow('[AUTO-MIGRATION]')} These fields are moved from "
                f"[project] to [tool.pdm] table: {updated_fields}",
                err=True,
            )
        return

    if not project.pyproject_file.exists() or not FORMATS["legacy"].check_fingerprint(
        project, project.pyproject_file
    ):
        return

    project.core.ui.echo(
        f"{termui.yellow('[AUTO-MIGRATION]')} Legacy pdm 0.x metadata detected, "
        "migrating to PEP 621...",
        err=True,
    )
    do_import(project, str(project.pyproject_file), "legacy")
    project.core.ui.echo(
        termui.green("pyproject.toml")
        + termui.yellow(
            " has been migrated to PEP 621 successfully. "
            "Now you can safely delete the legacy metadata under [tool.pdm] table."
        ),
        err=True,
    )


def check_update(project: Project) -> None:
    """Check if there is a new version of PDM available"""
    import sys
    from shlex import quote

    from pip._vendor.packaging.version import parse as parse_version

    from pdm.cli.utils import (
        is_homebrew_installation,
        is_pipx_installation,
        is_scoop_installation,
    )
    from pdm.utils import get_finder

    this_version = parse_version(project.core.version)
    candidate = get_finder([]).find_best_candidate("pdm")
    if not candidate.best_candidate or candidate.best_candidate.version <= this_version:
        return

    latest_version = candidate.best_candidate.version
    if is_pipx_installation():  # pragma: no cover
        install_command = "$ pipx upgrade pdm"
    elif is_scoop_installation():  # pragma: no cover
        install_command = "$ scoop update pdm"
    elif is_homebrew_installation():  # pragma: no cover
        install_command = "$ brew upgrade pdm"
    else:
        install_command = f"$ {quote(sys.executable)} -m pip install -U pdm"

    disable_command = "$ pdm config check_update false"

    message = [
        termui.blue(f"\nPDM {termui.cyan(str(this_version))}"),
        termui.blue(f" is installed, while {termui.cyan(str(latest_version))}"),
        termui.blue(" is available.\n"),
        termui.blue(f"Please run {termui.green(install_command, bold=True)}"),
        termui.blue(" to upgrade.\n"),
        termui.blue(f"Run {termui.green(disable_command, bold=True)}"),
        termui.blue(" to disable the check."),
    ]
    project.core.ui.echo("".join(message), err=True)
