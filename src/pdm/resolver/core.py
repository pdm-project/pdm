from __future__ import annotations

from typing import TYPE_CHECKING, Dict, cast

from pdm.models.candidates import Candidate
from pdm.models.repositories import BaseRepository
from pdm.models.requirements import strip_extras
from pdm.resolver.providers import BaseProvider
from pdm.resolver.python import PythonRequirement
from pdm.utils import normalize_name

if TYPE_CHECKING:
    from resolvelib.resolvers import Resolver

    from pdm.models.requirements import Requirement
    from pdm.models.specifiers import PySpecSet


def resolve(
    resolver: Resolver,
    requirements: list[Requirement],
    requires_python: PySpecSet,
    max_rounds: int = 10000,
) -> tuple[dict[str, Candidate], dict[tuple[str, str | None], list[Requirement]]]:
    """Core function to perform the actual resolve process.
    Return a tuple containing 2 items:

        1. A map of pinned candidates
        2. A map of resolved dependencies for each dependency group
    """
    requirements.append(PythonRequirement.from_pyspec_set(requires_python))
    provider = cast(BaseProvider, resolver.provider)
    repository = cast(BaseRepository, provider.repository)

    result = resolver.resolve(requirements, max_rounds)

    mapping = cast(Dict[str, Candidate], result.mapping)
    mapping.pop("python", None)

    local_name = normalize_name(repository.environment.project.name) if repository.environment.project.name else None
    for key, candidate in list(result.mapping.items()):
        if key is None:
            continue

        # For source distribution whose name can only be determined after it is built,
        # the key in the resolution map should be updated.
        if key.startswith(":empty:"):
            new_key = provider.identify(candidate)
            mapping[new_key] = mapping.pop(key)
            key = new_key

        if strip_extras(key)[0] == local_name:
            del mapping[key]

    return mapping, provider.fetched_dependencies
