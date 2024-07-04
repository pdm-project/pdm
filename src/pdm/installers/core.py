from __future__ import annotations

from typing import Iterable

from pdm.environments import BaseEnvironment
from pdm.installers.synchronizers import BaseSynchronizer
from pdm.models.requirements import Requirement
from pdm.resolver.core import resolve


def install_requirements(
    reqs: Iterable[Requirement], environment: BaseEnvironment, clean: bool = False, use_install_cache: bool = False
) -> None:  # pragma: no cover
    """Resolve and install the given requirements into the environment."""
    project = environment.project
    # Rewrite the python requires to only resolve for the current python version.
    provider = project.get_provider(env_spec=environment.spec)
    # Clear the overrides and excludes
    provider.overrides = {}
    provider.excludes = set()
    reqs = [req for req in reqs if not req.marker or req.marker.matches(provider.repository.env_spec)]
    reporter = project.get_reporter(reqs)
    resolver = project.core.resolver_class(provider, reporter)
    resolve_max_rounds = int(project.config["strategy.resolve_max_rounds"])
    backend = project.backend
    for req in reqs:
        if req.is_file_or_url:
            req.relocate(backend)  # type: ignore[attr-defined]
    resolved, _ = resolve(resolver, reqs, max_rounds=resolve_max_rounds, keep_self=True)
    syncer = BaseSynchronizer(resolved, environment, clean=clean, retry_times=0, use_install_cache=use_install_cache)
    syncer.synchronize()
