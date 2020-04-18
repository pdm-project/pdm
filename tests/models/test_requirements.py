import os

import pytest

from pdm.models.requirements import Requirement, RequirementError, parse_requirement
from tests import FIXTURES

FILE_PREFIX = "file:///" if os.name == "nt" else "file://"

REQUIREMENTS = [
    ("requests", ("requests", "*"), None),
    ("requests<2.21.0,>=2.20.0", ("requests", "<2.21.0,>=2.20.0"), None),
    (
        'requests==2.19.0; os_name == "nt"',
        ("requests", {"version": "==2.19.0", "marker": "os_name == 'nt'"}),
        None,
    ),
    (
        'requests[security,tests]==2.8.*,>=2.8.1; python_version < "2.7"',
        (
            "requests",
            {
                "version": "==2.8.*,>=2.8.1",
                "marker": "python_version < '2.7'",
                "extras": ["security", "tests"],
            },
        ),
        None,
    ),
    (
        "pip @ https://github.com/pypa/pip/archive/1.3.1.zip",
        ("pip", {"url": "https://github.com/pypa/pip/archive/1.3.1.zip"}),
        None,
    ),
    (
        "git+http://git.example.com/MyProject.git@master#egg=MyProject",
        ("MyProject", {"git": "http://git.example.com/MyProject.git", "ref": "master"}),
        None,
    ),
    (
        "https://github.com/pypa/pip/archive/1.3.1.zip",
        (None, {"url": "https://github.com/pypa/pip/archive/1.3.1.zip"}),
        None,
    ),
    (
        (FIXTURES / "projects/demo").as_posix(),
        ("demo", {"path": (FIXTURES / "projects/demo").as_posix()}),
        f"demo @ {FILE_PREFIX}" + (FIXTURES / "projects/demo").as_posix(),
    ),
    (
        (FIXTURES / "artifacts/demo-0.0.1-py2.py3-none-any.whl").as_posix(),
        (
            "demo",
            {
                "url": FILE_PREFIX
                + (FIXTURES / "artifacts/demo-0.0.1-py2.py3-none-any.whl").as_posix()
            },
        ),
        f"demo @ {FILE_PREFIX}"
        + (FIXTURES / "artifacts/demo-0.0.1-py2.py3-none-any.whl").as_posix(),
    ),
    (
        (FIXTURES / "projects/demo").as_posix() + "[security]",
        (
            "demo",
            {"path": (FIXTURES / "projects/demo").as_posix(), "extras": ["security"]},
        ),
        f"demo[security] @ {FILE_PREFIX}" + (FIXTURES / "projects/demo").as_posix(),
    ),
    (
        'requests; python_version=="3.7.*"',
        ("requests", {"version": "*", "marker": "python_version == '3.7.*'"}),
        'requests; python_version == "3.7.*"',
    ),
    (
        "git+git@github.com:pypa/pip.git#egg=pip",
        ("pip", {"git": "ssh://git@github.com/pypa/pip.git"}),
        "git+ssh://git@github.com/pypa/pip.git#egg=pip",
    ),
]


@pytest.mark.parametrize("req, req_dict, result", REQUIREMENTS)
def test_convert_req_dict_to_req_line(req, req_dict, result):
    r = parse_requirement(req)
    assert r.as_req_dict() == req_dict
    assert r.as_ireq()
    r = Requirement.from_req_dict(*req_dict)
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
