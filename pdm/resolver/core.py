from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Iterable, List, Optional, Set, Tuple

from pdm.models.candidates import identify
from pdm.models.markers import PySpecSet, join_metaset
from pdm.models.requirements import strip_extras
from resolvelib.resolvers import Criterion, Resolution

if TYPE_CHECKING:
    from resolvelib.resolvers import Result, Resolver
    from pdm.models.candidates import Candidate
    from pdm.models.markers import Marker
    from pdm.models.requirements import Requirement


# Monkey patch `resolvelib.resolvers.Resolution._merge_into_criterion`.
def _merge_into_criterion(self, requirement, parent):
    self._r.adding_requirement(requirement)
    name = self._p.identify(requirement)
    try:
        crit = self.state.criteria[name]
    except KeyError:
        crit = Criterion.from_requirement(self._p, requirement, parent)
    else:
        crit = crit.merged_with(self._p, requirement, parent)
    if not name:
        # For local packages, name is only available after candidate is resolved
        name = self._p.identify(requirement)
    return name, crit


Resolution._merge_into_criterion = _merge_into_criterion
del _merge_into_criterion


def _build_marker_and_pyspec(
    key: str,
    criterion: Criterion,
    pythons: Dict[str, PySpecSet],
    all_metasets: Dict[str, Tuple[Optional[Marker], PySpecSet]],
    keep_unresolved: Set[Optional[str]],
) -> Tuple[Optional[Marker], PySpecSet]:

    metasets = None

    for r, parent in criterion.information:
        if parent and identify(parent) in keep_unresolved:
            continue
        python = pythons[strip_extras(key)[0]]
        marker, pyspec = r.marker_no_python, r.requires_python
        pyspec = python & pyspec
        # Use 'and' to connect markers inherited from parent.
        if not parent:
            parent_metaset = None, PySpecSet()
        else:
            parent_metaset = all_metasets[identify(parent)]
        child_marker = (
            parent_metaset[0] & marker if any((parent_metaset[0], marker)) else None
        )
        child_pyspec = parent_metaset[1] & pyspec
        if not metasets:
            metasets = child_marker, child_pyspec
        else:
            # Use 'or' to connect metasets inherited from different parents.
            marker = metasets[0] | child_marker if any((child_marker, marker)) else None
            metasets = marker, metasets[1] | child_pyspec
    return metasets or (None, PySpecSet())


def _get_sections(crit: Criterion) -> Iterable[str]:
    for req, parent in crit.information:
        if not parent:
            yield req.from_section
        else:
            yield from parent.sections


def _calculate_markers_and_pyspecs(
    result: Result, pythons: Dict[str, PySpecSet]
) -> Dict[str, Tuple[Optional[Marker], PySpecSet]]:
    all_metasets = {}
    unresolved = {k for k in result.mapping}
    circular = {}

    while unresolved:
        new_metasets = {}
        for k in unresolved:
            crit = result.criteria[k]  # type: Criterion
            keep_unresolved = circular.get(k, set())
            # All parents must be resolved first
            if any(
                p and identify(p) in (unresolved - keep_unresolved)
                for p in crit.iter_parent()
            ):
                continue
            new_metasets[k] = _build_marker_and_pyspec(
                k, crit, pythons, all_metasets, keep_unresolved
            )
            result.mapping[k].sections = list(set(_get_sections(crit)))

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
                    (identify(p) for p in crit.iter_parent() if p),
                )
            )
            circular[package] = unresolved_parents

    for key in circular:
        crit = result.criteria[key]
        all_metasets[key] = _build_marker_and_pyspec(
            key, crit, pythons, all_metasets, set()
        )
        result.mapping[key].sections = list(set(_get_sections(crit)))

    return all_metasets


def _get_sections_from_top_requirements(traces):
    all_sections = {}
    for key, trace in traces.items():
        all_sections[key] = set(item[0][2:-2] for item in trace)
    return all_sections


def resolve(
    resolver: Resolver, requirements: List[Requirement], requires_python: PySpecSet
) -> Tuple[Dict[str, Candidate], Dict[str, Dict[str, Requirement]], Dict[str, str]]:
    provider, reporter = resolver.provider, resolver.reporter
    result = resolver.resolve(requirements)

    reporter.extract_metadata()
    all_metasets = _calculate_markers_and_pyspecs(
        result, provider.requires_python_collection
    )

    mapping = result.mapping

    for key, metaset in all_metasets.items():
        if key is None:
            continue
        # Root requires_python doesn't participate in the metaset resolving,
        # now check it!
        python = requires_python & metaset[1]
        if python.is_impossible:
            # Candidate doesn't match requires_python constraint
            del mapping[key]
        else:
            candidate = mapping[key]
            candidate.marker = join_metaset(metaset)
            candidate.hashes = provider.get_hashes(candidate)
    return mapping, provider.fetched_dependencies, provider.summary_collection
