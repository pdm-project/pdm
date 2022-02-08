import pytest

from pdm.models.markers import split_marker_extras


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
