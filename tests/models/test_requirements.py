import os

import pytest

from pdm.models.pip_shims import path_to_url
from pdm.models.requirements import RequirementError, parse_requirement
from tests import FIXTURES

FILE_PREFIX = "file:///" if os.name == "nt" else "file://"

REQUIREMENTS = [
    ("requests", None),
    ("requests<2.21.0,>=2.20.0", None),
    (
        'requests==2.19.0; os_name == "nt"',
        None,
    ),
    (
        'requests[security,tests]==2.8.*,>=2.8.1; python_version < "2.7"',
        None,
    ),
    (
        'pip @ https://github.com/pypa/pip/archive/1.3.1.zip ; python_version > "3.4"',
        'pip @ https://github.com/pypa/pip/archive/1.3.1.zip; python_version > "3.4"',
    ),
    (
        "git+http://git.example.com/MyProject.git@master#egg=MyProject",
        "MyProject @ git+http://git.example.com/MyProject.git@master",
    ),
    (
        "https://github.com/pypa/pip/archive/1.3.1.zip",
        None,
    ),
    (
        (FIXTURES / "projects/demo").as_posix(),
        "demo @ " + path_to_url((FIXTURES / "projects/demo")),
    ),
    (
        (FIXTURES / "artifacts/demo-0.0.1-py2.py3-none-any.whl").as_posix(),
        "demo @ "
        + path_to_url((FIXTURES / "artifacts/demo-0.0.1-py2.py3-none-any.whl")),
    ),
    (
        (FIXTURES / "projects/demo").as_posix() + "[security]",
        "demo[security] @ " + path_to_url((FIXTURES / "projects/demo")),
    ),
    (
        'requests; python_version=="3.7.*"',
        'requests; python_version == "3.7.*"',
    ),
    (
        "git+git@github.com:pypa/pip.git#egg=pip",
        "pip @ git+ssh://git@github.com/pypa/pip.git",
    ),
]


@pytest.mark.parametrize("req, result", REQUIREMENTS)
def test_convert_req_dict_to_req_line(req, result):
    r = parse_requirement(req)
    assert r.as_ireq()
    result = result or req
    assert r.as_line() == result


@pytest.mark.parametrize(
    "line,expected",
    [
        ("requests; os_name=>'nt'", "Invalid marker:"),
        ("./nonexist", r"The local path (.+)? does not exist"),
        ("./tests", r"The local path (.+)? is not installable"),
    ],
)
def test_illegal_requirement_line(line, expected):
    with pytest.raises(RequirementError, match=expected):
        parse_requirement(line)


@pytest.mark.parametrize(
    "line", ["requests >= 2.19.0", "https://github.com/pypa/pip/archive/1.3.1.zip"]
)
def test_not_supported_editable_requirement(line):
    with pytest.raises(
        RequirementError, match="Editable requirement is only supported"
    ):
        parse_requirement(line, True)
