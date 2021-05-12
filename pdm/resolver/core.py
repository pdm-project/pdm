from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from resolvelib.resolvers import Criterion, Resolution

from pdm.models.markers import PySpecSet
from pdm.models.requirements import strip_extras

if TYPE_CHECKING:
    from resolvelib.resolvers import Resolver

    from pdm.models.candidates import Candidate
    from pdm.models.requirements import Requirement

_old_merge_into_criterion = Resolution._merge_into_criterion


# Monkey patch `resolvelib.resolvers.Resolution._merge_into_criterion`.
def _merge_into_criterion(
    self, requirement: Requirement, parent: Optional[Candidate]
) -> Tuple[str, Criterion]:
    identifier, crit = _old_merge_into_criterion(self, requirement, parent)

    if not identifier:
        # For local packages, name is only available after candidate is resolved
        identifier = self._p.identify(requirement)
    return identifier, crit


Resolution._merge_into_criterion = _merge_into_criterion
del _merge_into_criterion


def resolve(
    resolver: Resolver,
    requirements: List[Requirement],
    requires_python: PySpecSet,
    max_rounds: int = 10000,
) -> Tuple[Dict[str, Candidate], Dict[str, List[Requirement]], Dict[str, str]]:
    """Core function to perform the actual resolve process.
    Return a tuple containing 3 items:

        1. A map of pinned candidates
        2. A map of resolved dependencies from each section of pyproject.toml
        3. A map of package descriptions fetched from PyPI source.
    """
    provider = resolver.provider
    result = resolver.resolve(requirements, max_rounds)

    mapping = result.mapping
    for key, candidate in list(result.mapping.items()):
        if key is None:
            continue
        # Root requires_python doesn't participate in the metaset resolving,
        # now check it!
        python = (
            requires_python & provider.requires_python_collection[strip_extras(key)[0]]
        )
        if python.is_impossible:
            # Remove candidates that don't match requires_python constraint
            del mapping[key]
        else:
            candidate.requires_python = str(python)
            candidate.hashes = provider.get_hashes(candidate)

    return mapping, provider.fetched_dependencies, provider.summary_collection
