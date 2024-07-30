import pytest

from pdm.models.markers import EnvSpec, get_marker
from pdm.models.specifiers import PySpecSet


@pytest.mark.parametrize(
    "original,marker,py_spec",
    [
        ("python_version > '3'", "", ">=3.1"),
        ("python_version > '3.8'", "", ">=3.9"),
        ("python_version != '3.8'", "", "!=3.8.*"),
        ("python_version == '3.7'", "", "==3.7.*"),
        ("python_version in '3.6 3.7'", "", ">=3.6.0,<3.8.0"),
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
    assert b == PySpecSet(py_spec)


@pytest.mark.parametrize(
    "marker,env_spec,expected",
    [
        ("os_name == 'nt'", EnvSpec.from_spec(">=3.10", "windows"), True),
        ("os_name == 'nt'", EnvSpec.from_spec(">=3.10"), True),
        ("os_name != 'nt'", EnvSpec.from_spec(">=3.10", "windows"), False),
        ("python_version >= '3.7' and os_name == 'nt'", EnvSpec.from_spec(">=3.10"), True),
        ("python_version < '3.7' and os_name == 'nt'", EnvSpec.from_spec(">=3.10"), False),
        ("python_version < '3.7' or os_name == 'nt'", EnvSpec.from_spec(">=3.10"), False),
        ("python_version >= '3.7' and os_name == 'nt'", EnvSpec.from_spec(">=3.10", "linux"), False),
        ("python_version >= '3.7' or os_name == 'nt'", EnvSpec.from_spec(">=3.10", "linux"), True),
        ("python_version >= '3.7' and implementation_name == 'pypy'", EnvSpec.from_spec(">=3.10"), True),
        (
            "python_version >= '3.7' and implementation_name == 'pypy'",
            EnvSpec.from_spec(">=3.10", implementation="cpython"),
            False,
        ),
    ],
)
def test_match_env_spec(marker, env_spec, expected):
    m = get_marker(marker)
    assert m.matches(env_spec) is expected
