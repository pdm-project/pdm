import os
import shutil
from argparse import Namespace
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import click
import tomlkit
from pip._vendor.pkg_resources import safe_name
from resolvelib.resolvers import ResolutionImpossible, ResolutionTooDeep

from pdm import termui
from pdm.cli.utils import (
    check_project_file,
    compatible_dev_flag,
    find_importable_files,
    format_lockfile,
    format_resolution_impossible,
    merge_dictionary,
    save_version_specifiers,
    set_env_in_reg,
    translate_sections,
)
from pdm.exceptions import NoPythonVersion, PdmUsageError, ProjectError
from pdm.formats import FORMATS
from pdm.formats.base import array_of_inline_tables, make_array, make_inline_table
from pdm.installers.installers import format_dist
from pdm.models.candidates import Candidate
from pdm.models.python import PythonInfo
from pdm.models.requirements import Requirement, parse_requirement, strip_extras
from pdm.models.specifiers import get_specifier
from pdm.project import Project
from pdm.resolver import resolve
from pdm.utils import setdefault

PEP582_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pep582")


def do_lock(
    project: Project,
    strategy: str = "all",
    tracked_names: Optional[Iterable[str]] = None,
    requirements: Optional[List[Requirement]] = None,
    dry_run: bool = False,
) -> Dict[str, Candidate]:
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
            resolver = project.core.resolver_class(provider, reporter)
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
    if not dry_run:
        project.write_lockfile(data)
    else:
        project.lockfile = data

    return mapping


def do_sync(
    project: Project,
    *,
    sections: Sequence[str] = (),
    dev: bool = True,
    default: bool = True,
    dry_run: bool = False,
    clean: bool = False,
    tracked_names: Optional[Sequence[str]] = None,
) -> None:
    """Synchronize project"""
    if not project.lockfile_file.exists():
        raise ProjectError("Lock file does not exist, nothing to sync")
    if tracked_names and dry_run:
        candidates = {
            name: c
            for name, c in project.get_locked_candidates("__all__").items()
            if name in tracked_names
        }
    else:
        candidates = {}
        sections = translate_sections(project, default, dev, sections or ())
        valid_sections = list(project.iter_sections())
        for section in sections:
            if section not in valid_sections:
                raise PdmUsageError(
                    f"Section {termui.green(repr(section))} doesn't exist "
                    "in the pyproject.toml"
                )
            candidates.update(project.get_locked_candidates(section))
    handler = project.core.synchronizer_class(
        candidates, project.environment, clean, dry_run
    )
    handler.synchronize()


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
    :param dev: add to dev dependencies section
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
    if not section:
        section = "dev" if dev else "default"
    tracked_names = set()
    requirements = {}
    for r in [parse_requirement(line, True) for line in editables] + [
        parse_requirement(line) for line in packages
    ]:
        key = r.identify()
        r.from_section = section
        tracked_names.add(key)
        requirements[key] = r
    project.core.ui.echo(
        f"Adding packages to {section} {'dev-' if dev else ''}dependencies: "
        + ", ".join(termui.green(key or "", bold=True) for key in requirements)
    )
    all_dependencies = project.all_dependencies
    all_dependencies.setdefault(section, {}).update(requirements)
    reqs = [r for deps in all_dependencies.values() for r in deps.values()]
    resolved = do_lock(project, strategy, tracked_names, reqs)

    # Update dependency specifiers and lockfile hash.
    save_version_specifiers(requirements, resolved, save)
    project.add_dependencies(requirements, section, dev)
    lockfile = project.lockfile
    project.write_lockfile(lockfile, False)

    if sync:
        do_sync(project, sections=(section,), default=False)


def do_update(
    project: Project,
    *,
    dev: Optional[bool] = None,
    sections: Sequence[str] = (),
    default: bool = True,
    strategy: str = "reuse",
    save: str = "compatible",
    unconstrained: bool = False,
    top: bool = False,
    dry_run: bool = False,
    packages: Sequence[str] = (),
) -> None:
    """Update specified packages or all packages"""
    check_project_file(project)
    if len(packages) > 0 and (top or len(sections) > 1 or not default):
        raise PdmUsageError(
            "packages argument can't be used together with multiple -s or "
            "--no-default and --top."
        )
    all_dependencies = project.all_dependencies
    updated_deps = {}
    if not packages:
        sections = translate_sections(
            project, default, compatible_dev_flag(project, dev), sections or ()
        )
        for section in sections:
            updated_deps.update(all_dependencies[section])
    else:
        section = sections[0] if sections else ("dev" if dev else "default")
        dependencies = all_dependencies[section]
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
                    "{} does not exist in {} {}dependencies.".format(
                        termui.green(name, bold=True), section, "dev-" if dev else ""
                    )
                )
            updated_deps[matched_name] = dependencies[matched_name]
        project.core.ui.echo(
            "Updating packages: {}.".format(
                ", ".join(termui.green(v, bold=True) for v in updated_deps)
            )
        )
    if unconstrained:
        for _, dep in updated_deps.items():
            dep.specifier = get_specifier("")
    reqs = [r for deps in all_dependencies.values() for r in deps.values()]
    resolved = do_lock(
        project,
        strategy if top or packages else "all",
        updated_deps.keys(),
        reqs,
        dry_run=dry_run,
    )
    do_sync(
        project,
        sections=sections,
        dev=dev,
        default=default,
        clean=False,
        dry_run=dry_run,
        tracked_names=updated_deps.keys() if top else None,
    )
    if unconstrained and not dry_run:
        # Need to update version constraints
        save_version_specifiers(updated_deps, resolved, save)
        project.add_dependencies(updated_deps, section, dev)
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
    if not section:
        section = "dev" if dev else "default"
    if section not in list(project.iter_sections()):
        raise ProjectError(f"No-exist section {section}")

    deps = project.get_pyproject_dependencies(section, dev)
    project.core.ui.echo(
        f"Removing packages from {section} {'dev-' if dev else ''}dependencies: "
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
                    termui.green(name, bold=True), section
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
    :param reverse: whether to display reverse graph.
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
        project.core.ui.echo(graph)
    else:
        rows = [
            (termui.green(k, bold=True), format_dist(v))
            for k, v in sorted(working_set.items())
        ]
        project.core.ui.display_columns(rows, ["Package", "Version"])


def do_build(
    project: Project,
    sdist: bool = True,
    wheel: bool = True,
    dest: str = "dist",
    clean: bool = True,
):
    """Build artifacts for distribution."""
    from pdm.builders import EnvSdistBuilder, EnvWheelBuilder

    if project.is_global:
        raise ProjectError("Not allowed to build based on the global project.")
    check_project_file(project)
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
            loc = EnvSdistBuilder(project.root, project.environment).build(dest)
            project.core.ui.echo(f"Built sdist at {loc}")
        if wheel:
            project.core.ui.echo("Building wheel...")
            loc = EnvWheelBuilder(project.root, project.environment).build(dest)
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


def do_use(
    project: Project, python: Optional[str] = "", first: Optional[bool] = False
) -> None:
    """Use the specified python version and save in project config.
    The python can be a version string or interpreter path.
    """

    def version_matcher(py_version: PythonInfo) -> bool:
        return project.python_requires.contains(str(py_version.version))

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

    old_path = project.config.get("python.path")
    new_path = selected_python.executable
    project.core.ui.echo(
        "Using Python interpreter: {} ({})".format(
            termui.green(str(new_path)),
            selected_python.identifier,
        )
    )
    project.python = selected_python
    if old_path and Path(old_path) != Path(new_path) and not project.is_global:
        project.core.ui.echo(termui.cyan("Updating executable scripts..."))
        project.environment.update_shebangs(new_path)


def do_import(
    project: Project,
    filename: str,
    format: Optional[str] = None,
    options: Optional[Namespace] = None,
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
        options = Namespace(dev=False, section=None)
    project_data, settings = FORMATS[key].convert(project, filename, options)
    pyproject = project.pyproject or tomlkit.document()

    if "tool" not in pyproject or "pdm" not in pyproject["tool"]:
        setdefault(pyproject, "tool", {})["pdm"] = tomlkit.table()

    if "project" not in pyproject:
        pyproject.add("project", tomlkit.table())
        pyproject["project"].add(tomlkit.comment("PEP 621 project metadata"))
        pyproject["project"].add(
            tomlkit.comment("See https://www.python.org/dev/peps/pep-0621/")
        )

    merge_dictionary(pyproject["project"], project_data)
    merge_dictionary(pyproject["tool"]["pdm"], settings)
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
    do_import(project, filepath, key)


def print_pep582_command(ui: termui.UI, shell: str = "AUTO"):
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
    ui.echo(result)


def migrate_pyproject(project: Project):
    """Migrate the legacy pyproject format to PEP 621"""

    if project.pyproject and "project" in project.pyproject:
        pyproject = project.pyproject
        settings = {}
        updated_fields = []
        for field in ("includes", "excludes", "build", "package-dir"):
            if field in pyproject["project"]:
                updated_fields.append(field)
                settings[field] = pyproject["project"][field]
                del pyproject["project"][field]
        if "dev-dependencies" in pyproject["project"]:
            if pyproject["project"]["dev-dependencies"]:
                settings["dev-dependencies"] = {
                    "dev": pyproject["project"]["dev-dependencies"]
                }
            del pyproject["project"]["dev-dependencies"]
            updated_fields.append("dev-dependencies")
        if updated_fields:
            if "tool" not in pyproject or "pdm" not in pyproject["tool"]:
                setdefault(pyproject, "tool", {})["pdm"] = tomlkit.table()
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
    do_import(project, project.pyproject_file, "legacy")
    project.core.ui.echo(
        termui.green("pyproject.toml")
        + termui.yellow(
            " has been migrated to PEP 621 successfully. "
            "Now you can safely delete the legacy metadata under [tool.pdm] table."
        ),
        err=True,
    )
