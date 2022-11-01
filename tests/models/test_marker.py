import pytest

from pdm.models.markers import Marker, split_marker_extras


@pytest.mark.parametrize(
    "original,extras,rest",
    [
        ("extra == 'foo'", {"foo"}, ""),
        ("extra != 'foo'", set(), 'extra != "foo"'),
        ("extra == 'foo' or extra == 'bar'", {"foo", "bar"}, ""),
        ("os_name == 'nt'", set(), 'os_name == "nt"'),
        ("extra in 'foo,bar'", {"foo", "bar"}, ""),
        (
            "os_name == 'nt' and (extra == 'foo' or extra == 'bar')",
            {"foo", "bar"},
            'os_name == "nt"',
        ),
        (
            'extra == "foo" and extra == "bar"',
            set(),
            'extra == "foo" and extra == "bar"',
        ),
        (
            "os_name == 'nt' and (extra == 'foo' or sys_platform == 'Windows')",
            set(),
            'os_name == "nt" and (extra == "foo" or sys_platform == "Windows")',
        ),
    ],
)
def test_split_marker_extras(original, extras, rest):
    result = split_marker_extras(original)
    assert result == (extras, rest)


@pytest.mark.parametrize(
    "original,marker,py_spec",
    [
        ("python_version > '3'", None, ">=3.1"),
        ("python_version > '3.8'", None, ">=3.9"),
        ("python_version != '3.8'", None, "!=3.8.*"),
        ("python_version == '3.7'", None, ">=3.7,<3.8"),
        ("python_version in '3.6 3.7'", None, ">=3.6,<3.8"),
        ("python_full_version >= '3.6.0'", None, ">=3.6"),
        ("python_full_version not in '3.8.3'", None, "!=3.8.3"),
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
    m = Marker(original)
    a, b = m.split_pyspec()
    assert marker == (str(a) if a is not None else None)
    assert py_spec == str(b)
