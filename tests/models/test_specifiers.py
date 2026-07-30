import pytest

from pdm.exceptions import InvalidPyVersion
from pdm.models.specifiers import PySpecSet, _convert_spec, _fix_py4k, get_specifier
from pdm.models.versions import Version


@pytest.mark.filterwarnings("ignore::FutureWarning")
@pytest.mark.parametrize(
    "original,normalized",
    [
        (">=3.6", ">=3.6"),
        ("<3.8", "<3.8"),
        ("~=2.7.0", "~=2.7.0"),
        ("", ""),
        (">=3.6,<3.8", "<3.8,>=3.6"),
        (">3.6", ">3.6"),
        ("<=3.7", "<=3.7"),
        (">=3.4.*", ">=3.4.0"),
        (">3.4.*", ">=3.4.0"),
        ("<=3.4.*", "<3.4.0"),
        ("<3.4.*", "<3.4.0"),
        (">=3.0+g1234", ">=3.0"),
        ("<3.0+g1234", "<3.0"),
        ("<3.10.0a6", "<3.10.0a6"),
        ("<3.10.2a3", "<3.10.2a3"),
    ],
)
def test_normalize_pyspec(original, normalized):
    spec = PySpecSet(original)
    assert str(spec) == normalized


@pytest.mark.parametrize(
    "left,right,result",
    [
        (">=3.6", ">=3.0", ">=3.6"),
        (">=3.6", "<3.8", "<3.8,>=3.6"),
        ("", ">=3.6", ">=3.6"),
        (">=3.6", "<3.2", "<empty>"),
        (">=2.7,!=3.0.*", "!=3.1.*", "!=3.0.*,!=3.1.*,>=2.7"),
        (">=3.11.0a2", "<3.11.0b", ">=3.11.0a2,<3.11.0b0"),
        ("<3.11.0a2", ">3.11.0b", "<empty>"),
    ],
)
def test_pyspec_and_op(left, right, result):
    left = PySpecSet(left)
    right = PySpecSet(right)
    assert left & right == PySpecSet(result)


@pytest.mark.parametrize(
    "left,right,result",
    [
        (">=3.6", ">=3.0", ">=3.0"),
        ("", ">=3.6", ""),
        (">=3.6", "<3.7", ""),
        (">=3.6,<3.8", ">=3.4,<3.7", "<3.8,>=3.4"),
        ("~=2.7", ">=3.6", "!=3.0.*,!=3.1.*,!=3.2.*,!=3.3.*,!=3.4.*,!=3.5.*,>=2.7"),
        ("<2.7.15", ">=3.0", "!=2.7.15,!=2.7.16,!=2.7.17,!=2.7.18"),
        (">3.11.0a2", ">3.11.0b", ">3.11.0a2"),
    ],
)
def test_pyspec_or_op(left, right, result):
    left = PySpecSet(left)
    right = PySpecSet(right)
    assert str(left | right) == result


def test_impossible_pyspec():
    spec = PySpecSet(">=3.6,<3.4")
    a = PySpecSet(">=2.7")
    assert spec.is_empty()
    assert (spec & a).is_empty()
    assert spec | a == a


@pytest.mark.filterwarnings("ignore::FutureWarning")
@pytest.mark.parametrize(
    "left,right",
    [
        ("~=2.7", ">=2.7"),
        (">=3.6", ""),
        (">=3.7", ">=3.6,<4.0"),
        (">=2.7,<3.0", ">=2.7,!=3.0.*,!=3.1.*,!=3.2.*,!=3.3.*"),
        (">=3.6", ">=2.7,!=3.0.*,!=3.1.*,!=3.2.*,!=3.3.*"),
        (
            ">=2.7,!=3.0.*,!=3.1.*,!=3.2.*,!=3.3.*,!=3.4.*,!=3.5.*",
            ">=2.7,!=3.0.*,!=3.1.*,!=3.2.*,!=3.3.*",
        ),
        (">=3.11.*", ">=3.11.0rc"),
    ],
)
def test_pyspec_is_subset_superset(left, right):
    left = PySpecSet(left)
    right = PySpecSet(right)
    assert left.is_subset(right), f"{left}, {right}"
    assert right.is_superset(left), f"{left}, {right}"


@pytest.mark.parametrize(
    "left,right",
    [
        ("~=2.7", ">=2.6,<2.7.15"),
        (">=3.7", ">=3.6,<3.9"),
        (">=3.7,<3.6", "==2.7"),
        (">=3.0,!=3.4.*", ">=2.7,!=3.0.*,!=3.1.*,!=3.2.*,!=3.3.*"),
        (">=3.11.0", "<3.11.0a"),
    ],
)
def test_pyspec_isnot_subset_superset(left, right):
    left = PySpecSet(left)
    right = PySpecSet(right)
    assert not left.is_subset(right), f"{left}, {right}"
    assert not left.is_superset(right), f"{left}, {right}"


def test_get_specifier_accepts_empty_values():
    assert str(get_specifier(None)) == ""
    assert str(get_specifier("*")) == ""
    assert str(get_specifier(">=3.9")) == ">=3.9"


def test_pyspec_rejects_invalid_version():
    with pytest.raises(InvalidPyVersion, match="Invalid specifier"):
        PySpecSet("not-a-specifier")


def test_pyspec_protocol_operations():
    spec = PySpecSet(">=3.9")
    logic = PySpecSet("<4")._logic

    assert spec.__eq__(object()) is NotImplemented
    assert spec & logic == PySpecSet(">=3.9,<4")
    assert spec | logic == PySpecSet()
    assert spec.__and__(object()) is NotImplemented
    assert spec.__or__(object()) is NotImplemented
    assert hash(spec) == hash(spec._logic)
    assert repr(spec) == "<PySpecSet >=3.9>"


@pytest.mark.parametrize(
    ("lower", "upper"),
    [
        ("3.9.0", "3.9.0"),
        ("2.7.0", "3.1.0"),
        ("3.9.0", "3.10.2"),
        ("3.9.1", "3.11.0"),
        ("3.9.1", "3.9.3"),
    ],
)
def test_populate_version_range_boundaries(lower, upper):
    assert list(PySpecSet._populate_version_range(Version(lower), Version(upper))) is not None


def test_superset_and_subset_shortcuts():
    empty = PySpecSet("<empty>")
    any_spec = PySpecSet()
    constrained = PySpecSet(">=3.9")

    assert not empty.is_superset(constrained)
    assert not empty.is_subset(constrained)
    assert any_spec.is_superset(">=3.9")
    assert constrained.is_subset("")


def test_as_marker_string_variants():
    assert PySpecSet().as_marker_string() == ""
    with pytest.raises(InvalidPyVersion, match="Impossible specifier"):
        PySpecSet("<empty>").as_marker_string()

    marker = PySpecSet(">=3.9,<4,!=3.10.*,!=3.11.1").as_marker_string()
    assert "python_version>='3.9'" in marker
    assert "3.10.0" in marker
    assert "3.11.1" in marker


def test_convert_union_specifier_and_fix_py4k():
    union = PySpecSet("<3.9")._logic | PySpecSet(">=3.11,<4")._logic

    assert " or " in _convert_spec(union)
    assert _fix_py4k(PySpecSet("<4.0")._logic).is_any()
    assert _fix_py4k(PySpecSet(">=3.9,<3.10")._logic) == PySpecSet(">=3.9,<3.10")._logic
