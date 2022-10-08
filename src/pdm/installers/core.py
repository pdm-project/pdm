from __future__ import annotations

from pdm.installers.manager import InstallManager
from pdm.models.environment import Environment
from pdm.models.requirements import Requirement
from pdm.models.specifiers import PySpecSet
from pdm.resolver.core import resolve
from pdm.termui import logger


def install_requirements(
    reqs: list[Requirement],
    environment: Environment,
    use_install_cache: bool = False,
) -> None:
    """Resolve and install the given requirements into the environment."""
    project = environment.project
    # Rewrite the python requires to only resolve for the current python version.
    environment.python_requires = PySpecSet(f"=={environment.interpreter.version}")
    provider = project.get_provider(ignore_compatibility=False)
    reporter = project.get_reporter(reqs)
    resolver = project.core.resolver_class(provider, reporter)
    resolve_max_rounds = int(project.config["strategy.resolve_max_rounds"])
    resolved, _ = resolve(
        resolver, reqs, environment.python_requires, max_rounds=resolve_max_rounds
    )
    manager = InstallManager(environment, use_install_cache=use_install_cache)
    for candidate in resolved.values():
        logger.info("Installing %s %s", candidate.name, candidate.version)
        manager.install(candidate)
