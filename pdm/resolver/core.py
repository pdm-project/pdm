from __future__ import annotations

from typing import TYPE_CHECKING, Dict, cast

from pdm.models.candidates import Candidate
from pdm.models.requirements import strip_extras
from pdm.resolver.providers import BaseProvider

if TYPE_CHECKING:
    from resolvelib.resolvers import Resolver

    from pdm.models.requirements import Requirement
    from pdm.models.specifiers import PySpecSet


def resolve(
    resolver: Resolver,
    requirements: list[Requirement],
    requires_python: PySpecSet,
    max_rounds: int = 10000,
) -> tuple[dict[str, Candidate], dict[str, list[Requirement]], dict[str, str]]:
    """Core function to perform the actual resolve process.
    Return a tuple containing 3 items:

        1. A map of pinned candidates
        2. A map of resolved dependencies for each dependency group
        3. A map of package descriptions fetched from PyPI source
    """
    provider = cast(BaseProvider, resolver.provider)
    result = resolver.resolve(requirements, max_rounds)

    mapping = cast(Dict[str, Candidate], result.mapping)
    for key, candidate in list(result.mapping.items()):
        if key is None:
            continue
        # For source distribution whose name can only be determined after it is built,
        # the key in the resolution map should be updated.
        if key.startswith(":empty:"):
            new_key = provider.identify(candidate)
            mapping[new_key] = mapping.pop(key)
            key = new_key
        # Root requires_python doesn't participate in the metaset resolving,
        # now check it!
        candidate_requires = provider.requires_python_collection[strip_extras(key)[0]]
        if (requires_python & candidate_requires).is_impossible:
            # Remove candidates that don't match requires_python constraint
            del mapping[key]
        else:
            candidate.requires_python = str(candidate_requires)
            candidate.hashes = provider.get_hashes(candidate)

    return mapping, provider.fetched_dependencies, provider.summary_collection
