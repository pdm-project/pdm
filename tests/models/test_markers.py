import pytest

from pdm.models.markers import Marker


@pytest.mark.parametrize(
    "expression,expected",
    [
        (Marker('os_name=="nt"') & None, 'os_name == "nt"'),
        (None & Marker('os_name=="nt"'), 'os_name == "nt"'),
        (
            Marker('os_name=="nt"') & Marker('python_version ~= "2.7"'),
            'os_name == "nt" and python_version ~= "2.7"',
        ),
        (
            Marker('os_name == "nt" and python_version ~= "2.7"')
            & Marker('sys_platform == "win32"'),
            'os_name == "nt" and python_version ~= "2.7" and sys_platform == "win32"',
        ),
        (
            Marker('os_name == "nt" or sys_platform == "win32"')
            & Marker('python_version ~= "2.7"'),
            '(os_name == "nt" or sys_platform == "win32") and python_version ~= "2.7"',
        ),
        (Marker('os_name == "nt"') | None, "None"),
        (None | Marker('os_name == "nt"'), "None"),
        (
            Marker('os_name == "nt"') | Marker('python_version ~= "2.7"'),
            'os_name == "nt" or python_version ~= "2.7"',
        ),
        (
            Marker('os_name == "nt" and python_version ~= "2.7"')
            | Marker('sys_platform == "win32"'),
            'os_name == "nt" and python_version ~= "2.7" or sys_platform == "win32"',
        ),
        (
            Marker('os_name=="nt" or sys_platform=="win32"')
            | Marker('python_version~="2.7"'),
            'os_name == "nt" or sys_platform == "win32" or python_version ~= "2.7"',
        ),
    ],
)
def test_marker_op(expression, expected):
    assert str(expression) == expected
