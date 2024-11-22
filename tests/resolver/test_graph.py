import itertools

from pdm.resolver.graph import OrderedSet


def test_ordered_set():
    elems = ["A", "bb", "c3"]
    all_sets = set()
    for case in itertools.permutations(elems):
        s = OrderedSet(case)
        all_sets.add(s)
        assert list(s) == list(case)
        assert len(s) == len(case)
        for e in elems:
            assert e in s
            assert e + "1" not in s
        assert str(s) == f"{{{', '.join(map(repr, case))}}}"
        assert repr(s) == f"OrderedSet({{{', '.join(map(repr, case))}}})"

    assert len(all_sets) == 1
