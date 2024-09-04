from __future__ import annotations

from typing import Iterable

from pdm.environments import BaseEnvironment
from pdm.installers.synchronizers import BaseSynchronizer
from pdm.models.requirements import Requirement
from pdm.resolver.reporters import LockReporter
from pdm.resolver.resolvelib import RLResolver


def install_requirements(
    reqs: Iterable[Requirement], environment: BaseEnvironment, clean: bool = False, use_install_cache: bool = False
) -> None:  # pragma: no cover
    """Resolve and install the given requirements into the environment."""
    reqs = [req for req in reqs if not req.marker or req.marker.matches(environment.spec)]
    reporter = LockReporter()
    project = environment.project
    backend = project.backend
    for req in reqs:
        if req.is_file_or_url:
            req.relocate(backend)  # type: ignore[attr-defined]
    resolver = project.get_resolver()(
        environment=environment,
        requirements=reqs,
        update_strategy="all",
        strategies=project.lockfile.default_strategies,
        target=environment.spec,
        tracked_names=(),
        keep_self=True,
        reporter=reporter,
    )
    if isinstance(resolver, RLResolver):
        resolver.provider.repository.find_dependencies_from_local = False
    resolved, *_ = resolver.resolve()
    syncer = BaseSynchronizer(resolved, environment, clean=clean, retry_times=0, use_install_cache=use_install_cache)
    syncer.synchronize()
