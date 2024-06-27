from __future__ import annotations

from typing import TYPE_CHECKING, AbstractSet, Iterable, Iterator, TypeVar, overload

from pdm.models.markers import Marker, get_marker

if TYPE_CHECKING:
    from resolvelib.resolvers import Criterion, Result

    from pdm.models.candidates import Candidate
    from pdm.models.requirements import Requirement

T = TypeVar("T")


class OrderedSet(AbstractSet[T]):
    """Set with deterministic ordering."""

    def __init__(self, iterable: Iterable[T] = ()) -> None:
        self._data = list(dict.fromkeys(iterable))

    def __hash__(self) -> int:
        return self._hash()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self})"

    def __str__(self) -> str:
        return f"{{{', '.join(map(repr, self._data))}}}"

    def __contains__(self, obj: object) -> bool:
        return obj in self._data

    def __iter__(self) -> Iterator[T]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)


@overload
def _identify_parent(parent: None) -> None: ...


@overload
def _identify_parent(parent: Candidate) -> str: ...


def _identify_parent(parent: Candidate | None) -> str | None:
    return parent.identify() if parent else None


def merge_markers(result: Result[Requirement, Candidate, str]) -> dict[str, Marker]:
    """Traverse through the parent dependencies till the top
    and merge any requirement markers on the path.
    Return a map of Metaset for each candidate.
    """
    all_markers: dict[str, Marker] = {}
    unresolved = OrderedSet(result.mapping)
    circular: dict[str, OrderedSet[str]] = {}

    while unresolved:
        new_markers: dict[str, Marker] = {}
        for k in unresolved:
            crit = result.criteria[k]
            keep_unresolved = circular.get(k, OrderedSet())
            # All parents must be resolved first
            if any(p and _identify_parent(p) in (unresolved - keep_unresolved) for p in crit.iter_parent()):
                continue
            new_markers[k] = _build_marker(crit, all_markers, keep_unresolved)

        if new_markers:
            all_markers.update(new_markers)
            unresolved -= new_markers  # type: ignore[assignment,operator]
        else:
            # No progress, there are likely circular dependencies.
            # Pick one package and keep its parents unresolved now, we will get into it
            # after all others are resolved.
            package = next((p for p in unresolved if p not in circular), None)
            if not package:
                break
            crit = result.criteria[package]
            unresolved_parents = OrderedSet(
                filter(
                    lambda p: p in unresolved and p != package,
                    (_identify_parent(p) for p in crit.iter_parent() if p),
                )
            )
            circular[package] = unresolved_parents

    for key in circular:
        crit = result.criteria[key]
        all_markers[key] = _build_marker(crit, all_markers, set())

    return all_markers


def _build_marker(
    crit: Criterion[Requirement, Candidate, str], resolved: dict[str, Marker], keep_unresolved: AbstractSet[str]
) -> Marker:
    marker = None

    for r, parent in crit.information:
        if parent and ((k := _identify_parent(parent)) in keep_unresolved or k not in resolved):
            continue
        this_marker = r.marker if r.marker is not None else get_marker("")
        # Use 'and' to connect markers inherited from parent.
        if not parent:
            parent_marker = get_marker("")
        else:
            parent_marker = resolved[_identify_parent(parent)]
        merged = this_marker & parent_marker
        # Use 'or' to connect metasets inherited from different parents.
        marker = marker | merged if marker is not None else merged
    return marker if marker is not None else get_marker("")


def populate_groups(result: Result[Requirement, Candidate, str]) -> None:
    """Find where the candidates come from by traversing
    the dependency tree back to the top.
    """

    resolved: dict[str, set[str]] = {}

    def get_candidate_groups(key: str) -> set[str]:
        if key in resolved:
            return resolved[key]
        res = resolved[key] = set()
        crit = result.criteria[key]
        for req, parent in crit.information:
            res.update(req.groups)
            if parent is not None:
                pkey = _identify_parent(parent)
                res.update(get_candidate_groups(pkey))
        return res

    for k, can in result.mapping.items():
        can.req.groups = sorted(get_candidate_groups(k))
