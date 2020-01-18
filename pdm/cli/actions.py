from typing import Optional, Tuple

from pdm.installers import Synchronizer
from pdm.project import Project


def do_sync(
    project: Project, sections: Tuple[str, ...], dev: bool,
    default: bool, dry_run: bool, clean: Optional[bool]
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
