from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Dict, cast

from pdm import termui
from pdm.models.candidates import Candidate
from pdm.models.repositories import BaseRepository
from pdm.models.requirements import strip_extras
from pdm.resolver.graph import merge_markers, populate_groups
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
    keep_self: bool = False,
    inherit_metadata: bool = False,
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

    if repository.has_warnings:
        repository.environment.project.core.ui.info(
            "Use `-q/--quiet` to suppress these warnings, or ignore them per-package with "
            r"`ignore_package_warnings` config in \[tool.pdm] table.",
            verbosity=termui.Verbosity.NORMAL,
        )

    mapping = cast(Dict[str, Candidate], result.mapping)
    mapping.pop("python", None)

    local_name = (
        normalize_name(repository.environment.project.name) if repository.environment.project.is_distribution else None
    )
    for key, candidate in list(mapping.items()):
        if key is None:
            continue
        # For source distribution whose name can only be determined after it is built,
        # the key in the resolution map and criteria should be updated.
        if key.startswith(":empty:"):
            new_key = provider.identify(candidate)
            mapping[new_key] = mapping.pop(key)
            result.criteria[new_key] = result.criteria.pop(key)

    if inherit_metadata:
        all_markers = merge_markers(result)
        populate_groups(result)
    else:
        all_markers = {}

    for key, candidate in list(mapping.items()):
        if key in all_markers:
            marker = all_markers[key]
            if marker.is_empty():
                del mapping[key]
                continue
            candidate.req = dataclasses.replace(candidate.req, marker=None if marker.is_any() else marker)

        if not keep_self and strip_extras(key)[0] == local_name:
            del mapping[key]

    return mapping, provider.fetched_dependencies
