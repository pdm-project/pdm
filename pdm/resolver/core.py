from __future__ import annotations

from typing import TYPE_CHECKING

from resolvelib.resolvers import Criterion, Resolution

from pdm.models.markers import PySpecSet
from pdm.models.requirements import strip_extras
from pdm.resolver.metaset import Metaset

if TYPE_CHECKING:
    from resolvelib.resolvers import Resolver, Result

    from pdm.models.candidates import Candidate
    from pdm.models.requirements import Requirement

_old_merge_into_criterion = Resolution._merge_into_criterion


# Monkey patch `resolvelib.resolvers.Resolution._merge_into_criterion`.
def _merge_into_criterion(
    self, requirement: Requirement, parent: Candidate | None
) -> tuple[str, Criterion]:
    identifier, crit = _old_merge_into_criterion(self, requirement, parent)

    if not identifier:
        # For local packages, name is only available after candidate is resolved
        identifier = self._p.identify(requirement)
    return identifier, crit


Resolution._merge_into_criterion = _merge_into_criterion
del _merge_into_criterion


def _identify_parent(parent: Candidate | None) -> None:
    return parent.identify() if parent else None


def _build_metaset(
    criterion: Criterion,
    all_metasets: dict[str, Metaset],
    keep_unresolved: set[str | None],
) -> Metaset:

    metaset = None

    for r, parent in criterion.information:
        if parent and _identify_parent(parent) in keep_unresolved:
            continue
        this_metaset = Metaset(r.marker)
        # Use 'and' to connect markers inherited from parent.
        if not parent:
            parent_metaset = Metaset()
        else:
            parent_metaset = all_metasets[_identify_parent(parent)]
        merged = this_metaset & parent_metaset
        # Use 'or' to connect metasets inherited from different parents.
        metaset = metaset | merged if metaset is not None else merged
    return metaset or Metaset()


def populate_sections(result: Result) -> None:
    """Determine where the candidates come from by traversing
    the dependency tree back to the top.
    """

    resolved: dict[str, set[str]] = {}

    def get_candidate_sections(key: str) -> set[str]:
        if key in resolved:
            return resolved[key]
        resolved[key] = res = set()
        crit: Criterion = result.criteria[key]
        for req, parent in crit.information:
            if parent is None:
                res.add(req.from_section)
            else:
                pkey = _identify_parent(parent)
                res.update(get_candidate_sections(pkey))
        return res

    for k, can in result.mapping.items():
        can.sections = sorted(get_candidate_sections(k))


def extract_metadata(result: Result) -> dict[str, Metaset]:
    """Traverse through the parent dependencies till the top
    and merge any requirement markers on the path.
    Return a map of Metaset for each candidate.
    """
    all_metasets: dict[str, Metaset] = {}
    unresolved: set[str] = {k for k in result.mapping}
    circular: dict[str, set[str]] = {}

    while unresolved:
        new_metasets = {}
        for k in unresolved:
            crit = result.criteria[k]
            keep_unresolved = circular.get(k, set())
            # All parents must be resolved first
            if any(
                p and _identify_parent(p) in (unresolved - keep_unresolved)
                for p in crit.iter_parent()
            ):
                continue
            new_metasets[k] = _build_metaset(crit, all_metasets, keep_unresolved)

        if new_metasets:
            all_metasets.update(new_metasets)
            for key in new_metasets:
                unresolved.remove(key)
        else:
            # No progress, there are likely circular dependencies.
            # Pick one package and keep its parents unresolved now, we will get into it
            # after all others are resolved.
            package = next((p for p in unresolved if p not in circular), None)
            if not package:
                break
            crit = result.criteria[package]
            unresolved_parents = set(
                filter(
                    lambda p: p in unresolved and p != package,
                    (_identify_parent(p) for p in crit.iter_parent() if p),
                )
            )
            circular[package] = unresolved_parents

    for key in circular:
        crit = result.criteria[key]
        all_metasets[key] = _build_metaset(crit, all_metasets, set())

    return all_metasets


def resolve(
    resolver: Resolver,
    requirements: list[Requirement],
    requires_python: PySpecSet,
    max_rounds: int = 1000,
) -> tuple[dict[str, Candidate], dict[str, list[Requirement]], dict[str, str]]:
    """Core function to perform the actual resolve process.
    Return a tuple containing 3 items:

        1. A map of pinned candidates
        2. A map of resolved dependencies from each section of pyproject.toml
        3. A map of package descriptions fetched from PyPI source.
    """
    provider, reporter = resolver.provider, resolver.reporter
    result = resolver.resolve(requirements, max_rounds)

    reporter.extract_metadata()
    all_metasets = extract_metadata(result)

    mapping = result.mapping

    for key, metaset in all_metasets.items():
        if key is None:
            continue
        # Root requires_python doesn't participate in the metaset resolving,
        # now check it!
        python = (
            requires_python
            & metaset.requires_python
            & provider.requires_python_collection[strip_extras(key)[0]]
        )
        if python.is_impossible:
            # Candidate doesn't match requires_python constraint
            del mapping[key]
        else:
            candidate = mapping[key]
            candidate.marker = metaset.as_marker()
            candidate.hashes = provider.get_hashes(candidate)

    populate_sections(result)
    return mapping, provider.fetched_dependencies, provider.summary_collection
