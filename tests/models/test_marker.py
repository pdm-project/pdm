import pytest

from pdm.models.markers import get_marker


@pytest.mark.parametrize(
    "original,marker,py_spec",
    [
        ("python_version > '3'", "", ">=3.1"),
        ("python_version > '3.8'", "", ">=3.9"),
        ("python_version != '3.8'", "", "!=3.8.*"),
        ("python_version == '3.7'", "", ">=3.7,<3.8"),
        ("python_version in '3.6 3.7'", "", ">=3.6,<3.8"),
        ("python_full_version >= '3.6.0'", "", ">=3.6"),
        ("python_full_version not in '3.8.3'", "", "!=3.8.3"),
        # mixed marker and python version
        ("python_version > '3.7' and os_name == 'nt'", 'os_name == "nt"', ">=3.8"),
        (
            "python_version > '3.7' or os_name == 'nt'",
            'python_version > "3.7" or os_name == "nt"',
            "",
        ),
    ],
)
def test_split_pyspec(original, marker, py_spec):
    m = get_marker(original)
    a, b = m.split_pyspec()
    assert marker == str(a)
    assert py_spec == str(b)
