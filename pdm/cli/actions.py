import json
import shutil
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import click
import pythonfinder
import tomlkit
from pkg_resources import safe_name

from pdm.builders import SdistBuilder, WheelBuilder
from pdm.cli.utils import (
    check_project_file,
    find_importable_files,
    format_lockfile,
    format_toml,
    save_version_specifiers,
)
from pdm.exceptions import NoPythonVersion, PdmUsageError, ProjectError
from pdm.formats import FORMATS
from pdm.installers.installers import format_dist
from pdm.iostream import stream
from pdm.models.candidates import Candidate
from pdm.models.requirements import Requirement, parse_requirement, strip_extras
from pdm.models.specifiers import get_specifier
from pdm.project import Project
from pdm.resolver import resolve
from pdm.utils import get_python_version


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

    with stream.open_spinner(
        title="Resolving dependencies", spinner="dots"
    ) as spin, stream.logging("lock"):
        reporter = project.get_reporter(requirements, tracked_names, spin)
        resolver = project.core.resolver_class(provider, reporter)
        mapping, dependencies, summaries = resolve(
            resolver, requirements, project.environment.python_requires
        )
        data = format_lockfile(mapping, dependencies, summaries)
        spin.succeed("Resolution success")
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
    lockfile["root"]["content_hash"] = "md5:" + project.get_content_hash("md5")
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
        lockfile["root"]["content_hash"] = "md5:" + project.get_content_hash("md5")
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
    toml_section = f"{section}-dependencies" if section != "default" else "dependencies"
    if toml_section not in project.tool_settings:
        raise ProjectError(
            f"No such section {stream.yellow(toml_section)} in pyproject.toml."
        )
    deps = project.tool_settings[toml_section]
    stream.echo(
        f"Removing packages from {section} dependencies: "
        + ", ".join(str(stream.green(name, bold=True)) for name in packages)
    )
    for name in packages:
        matched_name = next(
            filter(
                lambda k: safe_name(k).lower() == safe_name(name).lower(), deps.keys(),
            ),
            None,
        )
        if not matched_name:
            raise ProjectError(
                "{} does not exist in {} dependencies.".format(
                    stream.green(name, bold=True), section
                )
            )
        del deps[matched_name]

    project.write_pyproject()
    do_lock(project, "reuse")
    if sync:
        do_sync(project, sections=(section,), default=False, clean=True)


def do_list(project: Project, graph: bool = False) -> None:
    """Display a list of packages installed in the local packages directory.

    :param project: the project instance.
    :param graph: whether to display a graph.
    """
    from pdm.cli.utils import build_dependency_graph, format_dependency_graph

    check_project_file(project)
    working_set = project.environment.get_working_set()
    if graph:
        with project.environment.activate():
            dep_graph = build_dependency_graph(working_set)
        stream.echo(format_dependency_graph(dep_graph))
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
    ireq = project.make_self_candidate(False).ireq
    ireq.source_dir = project.root.as_posix()
    if clean:
        shutil.rmtree(dest, ignore_errors=True)
    if sdist:
        with SdistBuilder(ireq) as builder:
            builder.build(dest)
    if wheel:
        with WheelBuilder(ireq) as builder:
            builder.build(dest)


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
        "tool": {
            "pdm": {
                "name": name,
                "version": version,
                "description": "",
                "author": f"{author} <{email}>",
                "license": license,
                "homepage": "",
                "dependencies": tomlkit.table(),
                "dev-dependencies": tomlkit.table(),
            }
        },
        "build-system": {"requires": ["pdm"], "build-backend": "pdm.builders.api"},
    }
    if python_requires and python_requires != "*":
        get_specifier(python_requires)
        data["tool"]["pdm"]["python_requires"] = python_requires
    if not project.pyproject:
        project._pyproject = data
    else:
        project._pyproject.setdefault("tool", {})["pdm"] = data["tool"]["pdm"]
        project._pyproject["build-system"] = data["build-system"]
    project.write_pyproject()
    project.environment.write_site_py()


def do_use(project: Project, python: str, first: bool = False) -> None:
    """Use the specified python version and save in project config.
    The python can be a version string or interpreter path.
    """
    if python and not all(c.isdigit() for c in python.split(".")):
        if Path(python).exists():
            python_path = Path(python).absolute().as_posix()
        else:
            python_path = shutil.which(python)
        if not python_path:
            raise NoPythonVersion(f"{python} is not a valid Python.")
        python_version = get_python_version(python_path, True)
    else:
        finder = pythonfinder.Finder()
        pythons = []
        args = [int(v) for v in python.split(".") if v != ""]
        for i, entry in enumerate(finder.find_all_python_versions(*args)):
            python_version = get_python_version(entry.path.as_posix(), True)
            pythons.append((entry.path.as_posix(), python_version))
        if not pythons:
            raise NoPythonVersion(f"Python {python} is not available on the system.")

        if not first and len(pythons) > 1:
            for i, (path, python_version) in enumerate(pythons):
                stream.echo(f"{i}. {stream.green(path)} ({python_version})")
            selection = click.prompt(
                "Please select:",
                type=click.Choice([str(i) for i in range(len(pythons))]),
                default="0",
                show_choices=False,
            )
        else:
            selection = 0
        python_path, python_version = pythons[int(selection)]

    if not project.python_requires.contains(python_version):
        raise NoPythonVersion(
            "The target Python version {} doesn't satisfy "
            "the Python requirement: {}".format(python_version, project.python_requires)
        )
    stream.echo(
        "Using Python interpreter: {} ({})".format(
            stream.green(python_path), python_version
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
    python_path = project.environment.python_executable
    python_version = get_python_version(python_path, True)
    if not python and not show_project and not env:
        rows = [
            (stream.cyan("PDM version:", bold=True), project.core.version),
            (
                stream.cyan("Python Interpreter:", bold=True),
                python_path + f" ({python_version})",
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
    tool_settings = FORMATS[key].convert(project, filename)
    format_toml(tool_settings)

    if not project.pyproject_file.exists():
        project.pyproject = {"tool": {"pdm": {}}}
    project.tool_settings.update(tool_settings)
    project.pyproject["build-system"] = {
        "requires": ["pdm"],
        "build-backend": ["pdm.builders.api"],
    }
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
