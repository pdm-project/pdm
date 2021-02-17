import json
import os
import shutil
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import click
import tomlkit
from pip._vendor.pkg_resources import safe_name
from resolvelib.resolvers import ResolutionImpossible, ResolutionTooDeep

from pdm.cli.utils import (
    check_project_file,
    find_importable_files,
    find_python_in_path,
    format_lockfile,
    format_resolution_impossible,
    save_version_specifiers,
    set_env_in_reg,
)
from pdm.exceptions import NoPythonVersion, PdmUsageError, ProjectError
from pdm.formats import FORMATS
from pdm.formats.base import array_of_inline_tables, make_array, make_inline_table
from pdm.installers.installers import format_dist
from pdm.iostream import LOCK, stream
from pdm.models.builders import EnvBuilder
from pdm.models.candidates import Candidate
from pdm.models.in_process import get_python_version
from pdm.models.requirements import Requirement, parse_requirement, strip_extras
from pdm.models.specifiers import get_specifier
from pdm.project import Project
from pdm.resolver import resolve
from pdm.utils import get_python_version_string, setdefault

PEP582_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pep582")


def do_lock(
    project: Project,
    strategy: str = "all",
    tracked_names: Optional[Iterable[str]] = None,
    requirements: Optional[List[Requirement]] = None,
) -> Dict[str, Candidate]:
    """Performs the locking process and update lockfile.

    :param project: the project instance
    :param strategy: update stratege: reuse/eager/all
    :param tracked_names: required when using eager strategy
    :param requirements: An optional dictionary of requirements, read from pyproject
        if not given.
    """
    check_project_file(project)
    # TODO: multiple dependency definitions for the same package.
    provider = project.get_provider(strategy, tracked_names)
    if not requirements:
        requirements = [
            r for deps in project.all_dependencies.values() for r in deps.values()
        ]
    resolve_max_rounds = int(project.config["strategy.resolve_max_rounds"])
    with stream.logging("lock"):
        # The context managers are nested to ensure the spinner is stopped before
        # any message is thrown to the output.
        with stream.open_spinner(
            title="Resolving dependencies", spinner="dots"
        ) as spin:
            reporter = project.get_reporter(requirements, tracked_names, spin)
            resolver = project.core.resolver_class(provider, reporter)
            try:
                mapping, dependencies, summaries = resolve(
                    resolver,
                    requirements,
                    project.environment.python_requires,
                    resolve_max_rounds,
                )
            except ResolutionTooDeep:
                spin.fail(f"{LOCK} Lock failed")
                stream.echo(
                    "The dependency resolution exceeds the maximum loop depth of "
                    f"{resolve_max_rounds}, there may be some circular dependencies "
                    "in your project. Try to solve them or increase the "
                    f"{stream.green('`strategy.resolve_max_rounds`')} config.",
                    err=True,
                )
                raise
            except ResolutionImpossible as err:
                spin.fail(f"{LOCK} Lock failed")
                stream.echo(format_resolution_impossible(err), err=True)
                raise
            else:
                data = format_lockfile(mapping, dependencies, summaries)
                spin.succeed(f"{LOCK} Lock successful")
    project.write_lockfile(data)

    return mapping


def do_sync(
    project: Project,
    sections: Sequence[str] = (),
    dev: bool = False,
    default: bool = True,
    dry_run: bool = False,
    clean: Optional[bool] = None,
) -> None:
    """Synchronize project

    :param project: The project instance.
    :param sections: A tuple of optional sections to be synced.
    :param dev: whether to include dev-dependecies.
    :param default: whether to include default dependencies.
    :param dry_run: Print actions without actually running them.
    :param clean: whether to remove unneeded packages.
    """
    if not project.lockfile_file.exists():
        raise ProjectError("Lock file does not exist, nothing to sync.")
    clean = default if clean is None else clean
    candidates = {}
    for section in sections:
        candidates.update(project.get_locked_candidates(section))
    if dev:
        candidates.update(project.get_locked_candidates("dev"))
    if default:
        candidates.update(project.get_locked_candidates())
    handler = project.core.synchronizer_class(candidates, project.environment)
    handler.synchronize(clean=clean, dry_run=dry_run)


def do_add(
    project: Project,
    dev: bool = False,
    section: Optional[str] = None,
    sync: bool = True,
    save: str = "compatible",
    strategy: str = "reuse",
    editables: Iterable[str] = (),
    packages: Iterable[str] = (),
) -> None:
    """Add packages and install

    :param project: the project instance
    :param dev: add to dev dependencies seciton
    :param section: specify section to be add to
    :param sync: whether to install added packages
    :param save: save strategy
    :param strategy: update strategy
    :param editables: editable requirements
    :param packages: normal requirements
    """
    check_project_file(project)
    if not editables and not packages:
        raise PdmUsageError("Must specify at least one package or editable package.")
    section = "dev" if dev else section or "default"
    tracked_names = set()
    requirements = {}
    for r in [parse_requirement(line, True) for line in editables] + [
        parse_requirement(line) for line in packages
    ]:
        key = r.identify()
        r.from_section = section
        tracked_names.add(key)
        requirements[key] = r
    stream.echo(
        f"Adding packages to {section} dependencies: "
        + ", ".join(str(stream.green(key, bold=True)) for key in requirements)
    )
    all_dependencies = project.all_dependencies
    all_dependencies.setdefault(section, {}).update(requirements)
    reqs = [r for deps in all_dependencies.values() for r in deps.values()]
    resolved = do_lock(project, strategy, tracked_names, reqs)

    # Update dependency specifiers and lockfile hash.
    save_version_specifiers(requirements, resolved, save)
    project.add_dependencies(requirements)
    lockfile = project.lockfile
    project.write_lockfile(lockfile, False)

    if sync:
        do_sync(
            project,
            sections=(section,),
            dev=False,
            default=False,
            dry_run=False,
            clean=False,
        )


def do_update(
    project: Project,
    dev: bool = False,
    sections: Sequence[str] = (),
    default: bool = True,
    strategy: str = "reuse",
    save: str = "compatible",
    unconstrained: bool = False,
    packages: Sequence[str] = (),
) -> None:
    """Update specified packages or all packages

    :param project: The project instance
    :param dev: whether to update dev dependencies
    :param sections: update speicified sections
    :param default: update default
    :param strategy: update strategy (reuse/eager)
    :param save: save strategy (compatible/exact/wildcard)
    :param unconstrained: ignore version constraint
    :param packages: specified packages to update
    :return: None
    """
    check_project_file(project)
    if len(packages) > 0 and (len(sections) > 1 or not default):
        raise PdmUsageError(
            "packages argument can't be used together with multple -s or --no-default."
        )
    if not packages:
        if unconstrained:
            raise PdmUsageError(
                "--unconstrained must be used with package names given."
            )
        # pdm update with no packages given, same as 'lock' + 'sync'
        do_lock(project)
        do_sync(project, sections, dev, default, clean=False)
        return
    section = sections[0] if sections else ("dev" if dev else "default")
    all_dependencies = project.all_dependencies
    dependencies = all_dependencies[section]
    updated_deps = {}
    tracked_names = set()
    for name in packages:
        matched_name = next(
            filter(
                lambda k: safe_name(strip_extras(k)[0]).lower()
                == safe_name(name).lower(),
                dependencies.keys(),
            ),
            None,
        )
        if not matched_name:
            raise ProjectError(
                "{} does not exist in {} dependencies.".format(
                    stream.green(name, bold=True), section
                )
            )
        if unconstrained:
            dependencies[matched_name].specifier = get_specifier("")
        tracked_names.add(matched_name)
        updated_deps[matched_name] = dependencies[matched_name]
    stream.echo(
        "Updating packages: {}.".format(
            ", ".join(stream.green(v, bold=True) for v in tracked_names)
        )
    )
    reqs = [r for deps in all_dependencies.values() for r in deps.values()]
    resolved = do_lock(project, strategy, tracked_names, reqs)
    do_sync(project, sections=(section,), default=False, clean=False)
    if unconstrained:
        # Need to update version constraints
        save_version_specifiers(updated_deps, resolved, save)
        project.add_dependencies(updated_deps)
        lockfile = project.lockfile
        project.write_lockfile(lockfile, False)


def do_remove(
    project: Project,
    dev: bool = False,
    section: Optional[str] = None,
    sync: bool = True,
    packages: Sequence[str] = (),
):
    """Remove packages from working set and pyproject.toml

    :param project: The project instance
    :param dev: Remove package from dev-dependencies
    :param section: Remove package from given section
    :param sync: Whether perform syncing action
    :param packages: Package names to be removed
    :return: None
    """
    check_project_file(project)
    if not packages:
        raise PdmUsageError("Must specify at least one package to remove.")
    section = "dev" if dev else section or "default"
    if section not in list(project.iter_sections()):
        raise ProjectError(f"No {section} dependencies given in pyproject.toml.")

    deps = project.get_pyproject_dependencies(section)
    stream.echo(
        f"Removing packages from {section} dependencies: "
        + ", ".join(str(stream.green(name, bold=True)) for name in packages)
    )
    for name in packages:
        req = parse_requirement(name)
        matched_indexes = sorted(
            (i for i, r in enumerate(deps) if req.matches(r, False)), reverse=True
        )
        if not matched_indexes:
            raise ProjectError(
                "{} does not exist in {} dependencies.".format(
                    stream.green(name, bold=True), section
                )
            )
        for i in matched_indexes:
            del deps[i]

    project.write_pyproject()
    do_lock(project, "reuse")
    if sync:
        do_sync(project, sections=(section,), default=False, clean=True)


def do_list(project: Project, graph: bool = False, reverse: bool = False) -> None:
    """Display a list of packages installed in the local packages directory.

    :param project: the project instance.
    :param graph: whether to display a graph.
    :param reverse: wheter to display reverse graph.
    """
    from pdm.cli.utils import (
        build_dependency_graph,
        format_dependency_graph,
        format_reverse_dependency_graph,
    )

    check_project_file(project)
    working_set = project.environment.get_working_set()
    if reverse and not graph:
        raise PdmUsageError("--reverse must be used with --graph")
    if graph:
        with project.environment.activate():
            dep_graph = build_dependency_graph(working_set)
        if reverse:
            graph = format_reverse_dependency_graph(project, dep_graph)
        else:
            graph = format_dependency_graph(project, dep_graph)
        stream.echo(graph)
    else:
        rows = [
            (stream.green(k, bold=True), format_dist(v))
            for k, v in sorted(working_set.items())
        ]
        stream.display_columns(rows, ["Package", "Version"])


def do_build(
    project: Project,
    sdist: bool = True,
    wheel: bool = True,
    dest: str = "dist",
    clean: bool = True,
):
    """Build artifacts for distribution."""
    if project.is_global:
        raise ProjectError("Not allowed to build based on the global project.")
    check_project_file(project)
    if not wheel and not sdist:
        stream.echo("All artifacts are disabled, nothing to do.", err=True)
        return
    if not os.path.isabs(dest):
        dest = project.root.joinpath(dest).as_posix()
    if clean:
        shutil.rmtree(dest, ignore_errors=True)
    with stream.logging("build"), EnvBuilder(
        project.root, project.environment
    ) as builder:
        if sdist:
            stream.echo("Building sdist...")
            loc = builder.build_sdist(dest)
            stream.echo(f"Built sdist at {loc}")
        if wheel:
            stream.echo("Building wheel...")
            loc = builder.build_wheel(dest)
            stream.echo(f"Built wheel at {loc}")


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
            "dev-dependencies": make_array([], True),
            "requires-python": python_requires,
            "dynamic": ["classifiers"],
        },
        "build-system": {"requires": ["pdm-pep517"], "build-backend": "pdm.pep517.api"},
    }
    if python_requires and python_requires != "*":
        get_specifier(python_requires)
    if not project.pyproject:
        project._pyproject = data
    else:
        project._pyproject["project"] = data["project"]
        project._pyproject["build-system"] = data["build-system"]
    project.write_pyproject()


def do_use(project: Project, python: str, first: bool = False) -> None:
    """Use the specified python version and save in project config.
    The python can be a version string or interpreter path.
    """
    import pythonfinder

    python = python.strip()
    if python and not all(c.isdigit() for c in python.split(".")):
        if Path(python).exists():
            python_path = find_python_in_path(python)
        else:
            python_path = shutil.which(python)
        if not python_path:
            raise NoPythonVersion(f"{python} is not a valid Python.")
        python_version, is_64bit = get_python_version(python_path, True)
    else:
        finder = pythonfinder.Finder()
        pythons = []
        args = [int(v) for v in python.split(".") if v != ""]
        for i, entry in enumerate(finder.find_all_python_versions(*args)):
            python_version, is_64bit = get_python_version(entry.path.as_posix(), True)
            pythons.append((entry.path.as_posix(), python_version, is_64bit))
        if not pythons:
            raise NoPythonVersion(f"Python {python} is not available on the system.")

        if not first and len(pythons) > 1:
            for i, (path, python_version, is_64bit) in enumerate(pythons):
                stream.echo(
                    f"{i}. {stream.green(path)} "
                    f"({get_python_version_string(python_version, is_64bit)})"
                )
            selection = click.prompt(
                "Please select:",
                type=click.Choice([str(i) for i in range(len(pythons))]),
                default="0",
                show_choices=False,
            )
        else:
            selection = 0
        python_path, python_version, is_64bit = pythons[int(selection)]

    if not project.python_requires.contains(python_version):
        raise NoPythonVersion(
            "The target Python version {} doesn't satisfy "
            "the Python requirement: {}".format(python_version, project.python_requires)
        )
    stream.echo(
        "Using Python interpreter: {} ({})".format(
            stream.green(python_path),
            get_python_version_string(python_version, is_64bit),
        )
    )
    old_path = project.config.get("python.path")
    new_path = python_path
    project.project_config["python.path"] = Path(new_path).as_posix()
    if old_path and Path(old_path) != Path(new_path) and not project.is_global:
        stream.echo(stream.cyan("Updating executable scripts..."))
        project.environment.update_shebangs(new_path)


def do_info(
    project: Project,
    python: bool = False,
    show_project: bool = False,
    env: bool = False,
) -> None:
    """Show project information."""
    check_project_file(project)
    python_path = project.environment.python_executable
    python_version, is_64bit = get_python_version(python_path, True)
    if not python and not show_project and not env:
        rows = [
            (stream.cyan("PDM version:", bold=True), project.core.version),
            (
                stream.cyan("Python Interpreter:", bold=True),
                python_path
                + f" ({get_python_version_string(python_version, is_64bit)})",
            ),
            (stream.cyan("Project Root:", bold=True), project.root.as_posix()),
        ]
        stream.display_columns(rows)
        return

    if python:
        stream.echo(python_path)
    if show_project:
        stream.echo(project.root.as_posix())
    if env:
        stream.echo(json.dumps(project.environment.marker_environment, indent=2))


def do_import(project: Project, filename: str, format: Optional[str] = None) -> None:
    """Import project metadata from given file.

    :param project: the project instance
    :param filename: the file name
    :param format: the file format, or guess if not given.
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
    project_data, settings = FORMATS[key].convert(project, filename)
    pyproject = project.pyproject or tomlkit.document()

    if "tool" not in pyproject or "pdm" not in pyproject["tool"]:
        setdefault(pyproject, "tool", {})["pdm"] = tomlkit.table()

    pyproject["tool"]["pdm"].update(settings)

    if "project" not in pyproject:
        pyproject.add("project", tomlkit.table())
        pyproject["project"].add(tomlkit.comment("PEP 621 project metadata"))
        pyproject["project"].add(
            tomlkit.comment("See https://www.python.org/dev/peps/pep-0621/")
        )

    pyproject["project"].update(project_data)
    pyproject["build-system"] = {
        "requires": ["pdm-pep517"],
        "build-backend": "pdm.pep517.api",
    }
    project.pyproject = pyproject
    project.write_pyproject()


def ask_for_import(project: Project) -> None:
    """Show possible importable files and ask user to decide"""
    importable_files = list(find_importable_files(project))
    if not importable_files:
        return
    stream.echo(
        stream.cyan("Found following files from other formats that you may import:")
    )
    for i, (key, filepath) in enumerate(importable_files):
        stream.echo(f"{i}. {stream.green(filepath.as_posix())} ({key})")
    stream.echo(
        "{}. {}".format(
            len(importable_files),
            stream.yellow("don't do anything, I will import later."),
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
    do_import(project, filepath, key)


def print_pep582_command(shell: str = "AUTO"):
    """Print the export PYTHONPATH line to be evaluated by the shell."""
    import shellingham

    if os.name == "nt":
        set_env_in_reg("PYTHONPATH", PEP582_PATH)
        return
    lib_path = PEP582_PATH.replace("'", "\\'")
    if shell == "AUTO":
        shell = shellingham.detect_shell()[0]
    shell = shell.lower()
    if shell in ("zsh", "bash"):
        result = f"export PYTHONPATH='{lib_path}':$PYTHONPATH"
    elif shell == "fish":
        result = f"set -x PYTHONPATH '{lib_path}' $PYTHONPATH"
    elif shell in ("tcsh", "csh"):
        result = f"setenv PYTHONPATH '{lib_path}':$PYTHONPATH"
    else:
        raise PdmUsageError(
            f"Unsupported shell: {shell}, please specify another shell "
            "via `--pep582 <SHELL>`"
        )
    stream.echo(result)


def migrate_pyproject(project: Project):
    """Migrate the legacy pyproject format to PEP 621"""

    if (
        not project.pyproject_file.exists()
        or not FORMATS["legacy"].check_fingerprint(project, project.pyproject_file)
        or "project" in project.pyproject
    ):
        return

    stream.echo(
        stream.yellow("Legacy [tool.pdm] metadata detected, migrating to PEP 621..."),
        err=True,
    )
    do_import(project, project.pyproject_file, "legacy")
    stream.echo(
        stream.green("pyproject.toml")
        + stream.yellow(
            " has been migrated to PEP 621 successfully. "
            "Now you can safely delete the legacy metadata under [tool.pdm] table."
        ),
        err=True,
    )
