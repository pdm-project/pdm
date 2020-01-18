import copy

from pdm.models.markers import PySpecSet, join_metaset
from pdm.resolver.providers import BaseProvider, EagerUpdateProvider, ReusePinProvider  # noqa
from pdm.resolver.reporters import SimpleReporter  # noqa
from pdm.resolver.resolvers import Resolver


def _trace_visit_vertex(graph, current, target, visited, path, paths):
    if current == target:
        paths.append(path)
        return
    for v in graph.iter_children(current):
        if v == current or v in visited:
            continue
        next_path = path + [current]
        next_visited = visited | {current}
        _trace_visit_vertex(graph, v, target, next_visited, next_path, paths)


def trace_graph(graph):
    """Build a collection of "traces" for each package.

    A trace is a list of names that eventually leads to the package. For
    example, if A and B are root dependencies, A depends on C and D, B
    depends on C, and C depends on D, the return value would be like::

        {
            None: [],
            "A": [None],
            "B": [None],
            "C": [[None, "A"], [None, "B"]],
            "D": [[None, "B", "C"], [None, "A"]],
        }
    """
    result = {}
    for vertex in graph:
        result[vertex] = []
        for root in graph.iter_children(None):
            paths = []
            _trace_visit_vertex(graph, root, vertex, {None}, [None], paths)
            result[vertex].extend(paths)
    result.pop(None, None)
    return result


def _build_marker_and_pyspec(dependencies, pythons, key, trace, all_metasets):
    all_parent_metasets = {}
    for route in trace:
        parent = route[-1]
        if parent in all_parent_metasets:
            continue
        try:
            parent_metaset = all_metasets[parent]
        except KeyError:  # Parent not calculated yet. Wait for it.
            return
        all_parent_metasets[parent] = parent_metaset

    metasets = None
    for parent, parent_metaset in all_parent_metasets.items():
        r = dependencies[parent][key]
        python = pythons[key]
        marker, pyspec = r.marker_no_python, r.requires_python
        pyspec = python & pyspec
        # Use 'and' to connect markers inherited from parent.
        child_marker = (
            parent_metaset[0] & marker if any((parent_metaset[0], marker)) else None
        )
        child_pyspec = parent_metaset[1] & pyspec
        if not metasets:
            metasets = child_marker, child_pyspec
        else:
            # Use 'or' to connect metasets inherited from different parents.
            marker = metasets[0] | child_marker if any((metasets[0], marker)) else None
            metasets = marker, metasets[1] | child_pyspec
    return metasets or (None, PySpecSet())


def _calculate_markers_and_pyspecs(traces, dependencies, pythons):
    all_metasets = {None: (None, PySpecSet())}
    traces = copy.deepcopy(traces)

    while traces:
        new_metasets = {}
        for key, trace in traces.items():
            assert key not in all_metasets, key  # Sanity check for debug.
            metasets = _build_marker_and_pyspec(
                dependencies, pythons, key, trace, all_metasets,
            )
            if metasets is None:
                continue
            new_metasets[key] = metasets
        if not new_metasets:
            break  # No progress? Deadlocked. Give up.
        all_metasets.update(new_metasets)
        for key in new_metasets:
            del traces[key]

    return all_metasets


def _get_sections_from_top_requirements(traces, fetched_dependencies):
    all_sections = {}
    top_requirements = fetched_dependencies[None]
    for key, trace in traces.items():
        all_sections[key] = set([
            top_requirements[route[1]].from_section
            if len(route) > 1 else top_requirements[key].from_section
            for route in trace
        ])
    return all_sections


def resolve(provider, reporter, requirements, requires_python):
    resolver = Resolver(provider, reporter)
    state = resolver.resolve(requirements.values())
    provider.fetched_dependencies[None] = requirements
    traces = trace_graph(state.graph)
    all_metasets = _calculate_markers_and_pyspecs(
        traces, provider.fetched_dependencies, provider.requires_python_collection
    )
    all_sections = _get_sections_from_top_requirements(
        traces,
        provider.fetched_dependencies
    )
    for key, metaset in all_metasets.items():
        if key is None:
            continue
        # Root requires_python doesn't participate in the metaset resolving,
        # now check it!
        python = requires_python & metaset[1]
        if python.is_impossible:
            # Candidate doesn't match requires_python constraint
            del state.mapping[key]
        else:
            candidate = state.mapping[key]
            candidate.marker = join_metaset(metaset)
            candidate.sections = list(all_sections[key])
            candidate.hashes = provider.get_hashes(candidate)
    return state.mapping, provider.fetched_dependencies, provider.summary_collection
