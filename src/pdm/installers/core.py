from __future__ import annotations

from pdm import termui
from pdm.environments import BaseEnvironment
from pdm.installers.synchronizers import Synchronizer
from pdm.models.requirements import Requirement
from pdm.models.specifiers import PySpecSet
from pdm.resolver.core import resolve


def install_requirements(
    reqs: list[Requirement], environment: BaseEnvironment, use_install_cache: bool = False, clean: bool = False
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
    resolved, _ = resolve(
        resolver,
        reqs,
        environment.python_requires,
        max_rounds=resolve_max_rounds,
    )
    syncer = Synchronizer(resolved, environment, clean=clean, use_install_cache=use_install_cache, retry_times=0)
    with termui._console.capture():
        syncer.synchronize()
