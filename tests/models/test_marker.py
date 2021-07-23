import pytest

from pdm.models.markers import Marker, split_marker_extras


@pytest.mark.parametrize(
    "original,extras,rest",
    [
        ("extra == 'foo'", ["foo"], None),
        ("extra != 'foo'", [], "extra != 'foo'"),
        ("extra == 'foo' or extra == 'bar'", ["foo", "bar"], None),
        ("os_name == 'nt'", [], "os_name == 'nt'"),
        ("extra in 'foo,bar'", ["foo", "bar"], None),
        (
            "os_name == 'nt' and (extra == 'foo' or extra == 'bar')",
            ["foo", "bar"],
            "os_name == 'nt'",
        ),
        ("extra == 'foo' and extra == 'bar'", [], "extra == 'foo' and extra == 'bar'"),
        (
            "os_name == 'nt' and (extra == 'foo' or sys_platform == 'Windows')",
            [],
            "os_name == 'nt' and (extra == 'foo' or sys_platform == 'Windows')",
        ),
    ],
)
def test_split_marker_extras(original, extras, rest):
    result = split_marker_extras(Marker(original))
    assert result == (extras, Marker(rest) if rest else None)
