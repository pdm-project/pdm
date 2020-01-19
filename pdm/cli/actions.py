import itertools
import time
from typing import Dict, Iterable, Optional, Tuple

import tomlkit
from pdm.exceptions import PdmUsageError
from pdm.installers import Synchronizer
from pdm.models.candidates import Candidate, identify
from pdm.models.requirements import parse_requirement
from pdm.models.specifiers import bump_version, get_specifier
from pdm.project import Project
from pdm.resolver import (
    BaseProvider,
    EagerUpdateProvider,
    ReusePinProvider,
    SimpleReporter,
    resolve,
)


def format_lockfile(mapping, fetched_dependencies, summary_collection):
    packages = tomlkit.aot()
    metadata = tomlkit.table()
    for k, v in mapping.items():
        base = tomlkit.table()
        base.update(v.as_lockfile_entry())
        base.add("summary", summary_collection[k])
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


def do_lock(
    project: Project,
    strategy: str = "reuse",
    preferred_pins: Optional[Dict[str, Candidate]] = None,
    tracked_names: Optional[Iterable[str]] = None,
) -> Dict[str, Candidate]:
    """Performs the locking process and update lockfile.

    :param project: the project instance
    :param strategy: update stratege: reuse/eager
    :param preferred_pins: pins that will be reused if possible
    :param tracked_names: required when using eager strategy
    """
    # TODO: multiple dependency definitions for the same package.
    repository = project.get_repository()
    requirements = project.all_dependencies
    allow_prereleases = project.allow_prereleases
    requires_python = project.python_requires
    if not preferred_pins:
        provider = BaseProvider(repository, requires_python, allow_prereleases)
    else:
        provider_class = (
            ReusePinProvider if strategy == "reuse" else EagerUpdateProvider
        )
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
    reporter = SimpleReporter(flat_reqs)
    start = time.time()
    mapping, dependencies, summaries = resolve(
        provider, reporter, requirements, requires_python
    )
    data = format_lockfile(mapping, dependencies, summaries)
    project.write_lockfile(data)
    print("total time cost: {} s".format(time.time() - start))

    return mapping


def do_sync(
    project: Project,
    sections: Tuple[str, ...] = (),
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
    install: bool = True,
    save: str = "compatible",
    strategy: str = "reuse",
    editables: Iterable[str] = (),
    packages: Iterable[str] = (),
) -> None:
    """Add packages and install

    :param project: the project instance
    :param dev: add to dev dependencies seciton
    :param section: specify section to be add to
    :param install: whether to install added packages
    :param save: save strategy
    :param strategy: update strategy
    :param editables: editable requirements
    :param packages: normal requirements
    """
    if not editables and not packages:
        raise PdmUsageError("Must specify at least one package or editable package.")
    if dev:
        section = "dev"
    tracked_names = set()
    requirements = {}
    for r in [parse_requirement(line, True) for line in editables] + [
        parse_requirement(line) for line in packages
    ]:
        key = identify(r)
        r.from_section = section or "default"
        tracked_names.add(key)
        requirements[key] = r
    project.add_dependencies(requirements)
    resolved = do_lock(
        project, strategy, project.get_locked_candidates("__all__"), tracked_names
    )
    for name in tracked_names:
        r = requirements[name]
        if r.is_named and not r.specifier:
            if save == "exact":
                r.specifier = get_specifier(f"=={resolved[name].version}")
            elif save == "compatible":
                version = str(resolved[name].version)
                next_major_version = ".".join(
                    map(str, bump_version(tuple(version.split(".")), 0))
                )
                r.specifier = get_specifier(f">={version},<{next_major_version}")
    # Update dependency specifiers and lockfile hash.
    project.add_dependencies(requirements)
    lockfile = project.lockfile
    lockfile["root"]["content_hash"] = "md5:" + project.get_content_hash("md5")
    project.write_lockfile(lockfile)

    if install:
        do_sync(
            project,
            sections=(section,),
            dev=False,
            default=False,
            dry_run=False,
            clean=False,
        )
