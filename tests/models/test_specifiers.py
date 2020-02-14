import pytest

from pdm.models.specifiers import PySpecSet


@pytest.mark.parametrize(
    "original,normalized",
    [
        (">=3.6", ">=3.6"),
        ("<3.8", "<3.8"),
        ("~=2.7.0", ">=2.7,<2.8"),
        ("", ""),
        (">=3.6,<3.8", ">=3.6,<3.8"),
        (">3.6", ">=3.6.1"),
        ("<=3.7", "<3.7.1"),
        (">=3.6,!=3.4.*", ">=3.6"),
        (">=3.6,!=3.6.*", ">=3.7"),
        (">=3.6,<3.8,!=3.8.*", ">=3.6,<3.8"),
    ],
)
def test_normalize_pyspec(original, normalized):
    spec = PySpecSet(original)
    assert str(spec) == normalized


@pytest.mark.parametrize(
    "left,right,result",
    [
        (">=3.6", ">=3.0", ">=3.6"),
        (">=3.6", "<3.8", ">=3.6,<3.8"),
        ("", ">=3.6", ">=3.6"),
        (">=3.6", "<3.2", "impossible"),
        (">=2.7,!=3.0.*", "!=3.1.*", ">=2.7,!=3.0.*,!=3.1.*"),
    ],
)
def test_pyspec_and_op(left, right, result):
    left = PySpecSet(left)
    right = PySpecSet(right)
    assert str(left & right) == result


@pytest.mark.parametrize(
    "left,right,result",
    [
        (">=3.6", ">=3.0", ">=3.0"),
        ("", ">=3.6", ""),
        (">=3.6", "<3.7", ""),
        (">=3.6,<3.8", ">=3.4,<3.7", ">=3.4,<3.8"),
        ("~=2.7", ">=3.6", ">=2.7,!=3.0.*,!=3.1.*,!=3.2.*,!=3.3.*,!=3.4.*,!=3.5.*"),
        ("<3.6.5", ">=3.7", "!=3.6.5,!=3.6.6,!=3.6.7,!=3.6.8,!=3.6.9,!=3.6.10"),
    ],
)
def test_pyspec_or_op(left, right, result):
    left = PySpecSet(left)
    right = PySpecSet(right)
    assert str(left | right) == result


def test_impossible_pyspec():
    spec = PySpecSet(">=3.6,<3.4")
    a = PySpecSet(">=2.7")
    assert spec.is_impossible
    assert (spec & a).is_impossible
    assert spec | a == a
    spec_copy = spec.copy()
    assert spec_copy.is_impossible
    assert str(spec_copy) == "impossible"
