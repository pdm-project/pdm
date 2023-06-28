from __future__ import annotations

from pdm.environments import BaseEnvironment
from pdm.installers.synchronizers import BaseSynchronizer
from pdm.models.requirements import Requirement
from pdm.models.specifiers import PySpecSet
from pdm.resolver.core import resolve


def install_requirements(
    reqs: list[Requirement], environment: BaseEnvironment, clean: bool = False, use_install_cache: bool = False
) -> None:  # pragma: no cover
    """Resolve and install the given requirements into the environment."""
    project = environment.project
    # Rewrite the python requires to only resolve for the current python version.
    environment.python_requires = PySpecSet(f"=={environment.interpreter.version}")
    provider = project.get_provider(ignore_compatibility=False)
    reporter = project.get_reporter(reqs)
    resolver = project.core.resolver_class(provider, reporter)
    resolve_max_rounds = int(project.config["strategy.resolve_max_rounds"])
    backend = project.backend
    for req in reqs:
        if req.is_file_or_url:
            req.relocate(backend)  # type: ignore[attr-defined]
    resolved, _ = resolve(resolver, reqs, environment.python_requires, max_rounds=resolve_max_rounds, keep_self=True)
    syncer = BaseSynchronizer(resolved, environment, clean=clean, retry_times=0, use_install_cache=use_install_cache)
    syncer.synchronize()
