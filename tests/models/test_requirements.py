from __future__ import annotations

import os

import pytest

from pdm.models.requirements import RequirementError, filter_requirements_with_extras, parse_requirement
from pdm.utils import PACKAGING_22, path_to_url
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
        None,
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
        "demo @ " + path_to_url(FIXTURES / "projects/demo"),
    ),
    (
        (FIXTURES / "artifacts/demo-0.0.1-py2.py3-none-any.whl").as_posix(),
        "demo @ " + path_to_url(FIXTURES / "artifacts/demo-0.0.1-py2.py3-none-any.whl"),
    ),
    (
        (FIXTURES / "projects/demo").as_posix() + "[security]",
        "demo[security] @ " + path_to_url(FIXTURES / "projects/demo"),
    ),
    (
        'requests; python_version=="3.7.*"',
        'requests; python_version == "3.7.*"',
    ),
    (
        "git+git@github.com:pypa/pip.git#egg=pip",
        "pip @ git+ssh://git@github.com/pypa/pip.git",
    ),
    pytest.param(
        "foo >=4.*, <=5.*",
        "foo<5.0,>=4.0",
        marks=pytest.mark.skipif(not PACKAGING_22, reason="packaging 22+ required"),
    ),
    pytest.param(
        "foo (>=4.*, <=5.*)",
        "foo<5.0,>=4.0",
        marks=pytest.mark.skipif(not PACKAGING_22, reason="packaging 22+ required"),
    ),
    pytest.param(
        "foo>=3.0+g1234; python_version>='3.6'",
        'foo>=3.0; python_version >= "3.6"',
        marks=pytest.mark.skipif(not PACKAGING_22, reason="packaging 22+ required"),
    ),
]


def filter_requirements_to_lines(
    requirements: list[str], extras: tuple[str, ...], include_default: bool = False
) -> list[str]:
    return [
        req.as_line() for req in filter_requirements_with_extras(requirements, extras, include_default=include_default)
    ]


@pytest.mark.filterwarnings("ignore::FutureWarning")
@pytest.mark.parametrize("req, result", REQUIREMENTS)
def test_convert_req_dict_to_req_line(req, result):
    r = parse_requirement(req)
    result = result or req
    assert r.as_line() == result


@pytest.mark.parametrize(
    "line,expected",
    [
        ("requests; os_name=>'nt'", None),
        ("django>=2<4", None),
    ],
)
def test_illegal_requirement_line(line, expected):
    with pytest.raises(RequirementError, match=expected):
        parse_requirement(line)


@pytest.mark.parametrize("line", ["requests >= 2.19.0", "https://github.com/pypa/pip/archive/1.3.1.zip"])
def test_not_supported_editable_requirement(line):
    with pytest.raises(RequirementError, match="Editable requirement is only supported"):
        parse_requirement(line, True)


def test_filter_requirements_with_extras():
    requirements = [
        "foo; extra == 'a'",
        "bar; extra == 'b'",
        "baz; extra == 'a' or extra == 'b'",
        "qux; extra == 'a' and extra == 'b'",
        "ping; os_name == 'nt' and extra == 'a'",
        "blah",
    ]
    assert filter_requirements_to_lines(requirements, ()) == ["blah"]
    assert filter_requirements_to_lines(requirements, ("a",)) == ["foo", "baz", 'ping; os_name == "nt"']
    assert filter_requirements_to_lines(requirements, ("b",)) == ["bar", "baz"]
    assert filter_requirements_to_lines(requirements, ("a", "b")) == [
        "foo",
        "bar",
        "baz",
        "qux",
        'ping; os_name == "nt"',
    ]
    assert filter_requirements_to_lines(requirements, ("c",)) == []
    assert filter_requirements_to_lines(requirements, ("a", "b"), include_default=True) == [
        "foo",
        "bar",
        "baz",
        "qux",
        'ping; os_name == "nt"',
        "blah",
    ]
