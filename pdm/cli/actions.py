import itertools
import json
import shutil
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence

from pkg_resources import safe_name

import click
import halo
import pythonfinder
import tomlkit
from pdm.builders import SdistBuilder, WheelBuilder
from pdm.context import context
from pdm.exceptions import NoPythonVersion, ProjectError
from pdm.installers import Synchronizer, format_dist
from pdm.models.candidates import Candidate, identify
from pdm.models.requirements import Requirement, parse_requirement, strip_extras
from pdm.models.specifiers import bump_version, get_specifier
from pdm.project import Project
from pdm.resolver import BaseProvider, EagerUpdateProvider, ReusePinProvider, resolve
from pdm.resolver.reporters import SpinnerReporter
from pdm.utils import get_python_version


def format_lockfile(mapping, fetched_dependencies, summary_collection):
    """Format lock file from a dict of resolved candidates, a mapping of dependencies
    and a collection of package summaries.
    """
    packages = tomlkit.aot()
    metadata = tomlkit.table()
    for k, v in sorted(mapping.items()):
        base = tomlkit.table()
        base.update(v.as_lockfile_entry())
        base.add("summary", summary_collection[strip_extras(k)[0]])
        deps = tomlkit.table()
        for r in fetched_dependencies[k].values():
            name, req = r.as_req_dict()
            if getattr(req, "items", None) is not None:
                inline = tomlkit.inline_table()
                inline.update(req)
                deps.add(name, inline)
            else:
                deps.add(name, req)
        if len(deps) > 0:
            base.add("dependencies", deps)
        packages.append(base)
        if v.hashes:
            key = f"{k} {v.version}"
            array = tomlkit.array()
            array.multiline(True)
            for filename, hash_value in v.hashes.items():
                inline = tomlkit.inline_table()
                inline.update({"file": filename, "hash": hash_value})
                array.append(inline)
            if array:
                metadata.add(key, array)
    doc = tomlkit.document()
    doc.update({"package": packages, "metadata": metadata})
    return doc


def save_version_specifiers(
    requirements: Dict[str, Requirement],
    resolved: Dict[str, Candidate],
    save_strategy: str,
) -> None:
    """Rewrite the version specifiers according to the resolved result and save strategy

    :param requirements: the requirements to be updated
    :param resolved: the resolved mapping
    :param save_strategy: compatible/wildcard/exact
    """
    for name, r in requirements.items():
        if r.is_named and not r.specifier:
            if save_strategy == "exact":
                r.specifier = get_specifier(f"=={resolved[name].version}")
            elif save_strategy == "compatible":
                version = str(resolved[name].version)
                next_major_version = ".".join(
                    map(str, bump_version(tuple(version.split(".")), 0))
                )
                r.specifier = get_specifier(f">={version},<{next_major_version}")


def check_project_file(project: Project) -> None:
    """Check the existence of the project file and throws an error on failure."""
    if not project.tool_settings:
        raise ProjectError(
            "The pyproject.toml has not been initialized yet. You can do this "
            "by running {}.".format(context.io.green("'pdm init'"))
        )


def do_lock(
    project: Project,
    strategy: str = "all",
    tracked_names: Optional[Iterable[str]] = None,
    requirements: Optional[Dict[str, Dict[str, Requirement]]] = None,
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
    repository = project.get_repository()
    requirements = requirements or project.all_dependencies
    allow_prereleases = project.allow_prereleases
    requires_python = project.python_requires
    if strategy == "all":
        provider = BaseProvider(repository, requires_python, allow_prereleases)
    else:
        provider_class = (
            ReusePinProvider if strategy == "reuse" else EagerUpdateProvider
        )
        preferred_pins = project.get_locked_candidates("__all__")
        provider = provider_class(
            preferred_pins,
            tracked_names or (),
            repository,
            requires_python,
            allow_prereleases,
        )
    flat_reqs = list(
        itertools.chain(*[deps.values() for _, deps in requirements.items()])
    )
    # TODO: switch reporter at io level.
    with halo.Halo(text="Resolving dependencies", spinner="dots") as spin:
        reporter = SpinnerReporter(flat_reqs, spin)
        mapping, dependencies, summaries = resolve(
            provider, reporter, requirements, requires_python
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
    handler = Synchronizer(candidates, project.environment)
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
        raise click.BadParameter(
            "Must specify at least one package or editable package."
        )
    section = "dev" if dev else section or "default"
    tracked_names = set()
    requirements = {}
    for r in [parse_requirement(line, True) for line in editables] + [
        parse_requirement(line) for line in packages
    ]:
        key = identify(r)
        r.from_section = section
        tracked_names.add(key)
        requirements[key] = r
    context.io.echo(
        f"Adding packages to {section} dependencies: "
        + ", ".join(str(context.io.green(key, bold=True)) for key in requirements)
    )
    all_dependencies = project.all_dependencies
    all_dependencies.setdefault(section, {}).update(requirements)
    resolved = do_lock(project, strategy, tracked_names, all_dependencies)

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
        raise click.BadParameter(
            "packages argument can't be used together with multple -s or --no-default."
        )
    if not packages:
        if unconstrained:
            raise click.BadArgumentUsage(
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
                    context.io.green(name, bold=True), section
                )
            )
        if unconstrained:
            dependencies[matched_name].specifier = get_specifier("")
        tracked_names.add(matched_name)
        updated_deps[matched_name] = dependencies[matched_name]
    context.io.echo(
        "Updating packages: {}.".format(
            ", ".join(context.io.green(v, bold=True) for v in tracked_names)
        )
    )
    resolved = do_lock(project, strategy, tracked_names, all_dependencies)
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
        raise click.BadParameter("Must specify at least one package to remove.")
    section = "dev" if dev else section or "default"
    toml_section = f"{section}-dependencies" if section != "default" else "dependencies"
    if toml_section not in project.tool_settings:
        raise ProjectError(
            f"No such section {context.io.yellow(toml_section)} in pyproject.toml."
        )
    deps = project.tool_settings[toml_section]
    context.io.echo(
        f"Removing packages from {section} dependencies: "
        + ", ".join(str(context.io.green(name, bold=True)) for name in packages)
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
                    context.io.green(name, bold=True), section
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
    from pdm.cli.dependencies import build_dependency_graph, format_dependency_graph

    check_project_file(project)
    working_set = project.environment.get_working_set()
    if graph:
        with project.environment.activate():
            dep_graph = build_dependency_graph(working_set)
        context.io.echo(format_dependency_graph(dep_graph))
    else:
        rows = [
            (context.io.green(k, bold=True), format_dist(v))
            for k, v in sorted(working_set.items())
        ]
        context.io.display_columns(rows, ["Package", "Version"])


def do_build(
    project: Project,
    sdist: bool = True,
    wheel: bool = True,
    dest: str = "dist",
    clean: bool = True,
):
    """Build artifacts for distribution."""
    check_project_file(project)
    if not wheel and not sdist:
        context.io.echo("All artifacts are disabled, nothing to do.", err=True)
        return
    ireq = project.make_self_candidate(False).ireq
    ireq.source_dir = "."
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
    if not project.pyproject:
        project._pyproject = data
    else:
        project._pyproject.setdefault("tool", {})["pdm"] = data["tool"]["pdm"]
        project._pyproject["build-system"] = data["build-system"]
    project.write_pyproject()


def do_use(project: Project, python: str) -> None:
    """Use the specified python version and save in project config.
    The python can be a version string or interpreter path.
    """
    if Path(python).is_absolute():
        python_path = python
    else:
        python_path = shutil.which(python)
        if not python_path:
            finder = pythonfinder.Finder()
            try:
                python_path = finder.find_python_version(python).path.as_posix()
            except AttributeError:
                raise NoPythonVersion(f"Python {python} is not found on the system.")

    python_version = get_python_version(python_path, True)
    if not project.python_requires.contains(python_version):
        raise NoPythonVersion(
            "The target Python version {} doesn't satisfy "
            "the Python requirement: {}".format(python_version, project.python_requires)
        )
    context.io.echo(
        "Using Python interpreter: {} ({})".format(
            context.io.green(python_path), python_version
        )
    )

    project.config["python.path"] = Path(python_path).as_posix()
    project.config.save_config()


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
            (
                context.io.cyan("Python Interpreter:", bold=True),
                python_path + f" ({python_version})",
            ),
            (context.io.cyan("Project Root:", bold=True), project.root.as_posix()),
        ]
        context.io.display_columns(rows)
        return

    if python:
        context.io.echo(python_path)
    if show_project:
        context.io.echo(project.root.as_posix())
    if env:
        context.io.echo(json.dumps(project.environment.marker_environment, indent=2))
