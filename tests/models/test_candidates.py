import pytest

from pdm.exceptions import ExtrasError
from pdm.models.candidates import Candidate
from pdm.models.requirements import parse_requirement
from tests import FIXTURES


@pytest.mark.parametrize(
    "requirement_line",
    [
        f"{(FIXTURES / 'projects/demo').as_posix()}",
        "git+https://github.com/test-root/demo.git#egg=demo",
    ],
)
def test_parse_vcs_directory_metadata(requirement_line, project, vcs, is_editable):
    req = parse_requirement(requirement_line, is_editable)
    candidate = Candidate(req, project.environment)
    assert candidate.get_dependencies_from_metadata() == [
        "idna",
        'chardet; os_name == "nt"',
    ]
    assert candidate.name == "demo"
    assert candidate.version == "0.0.1"


@pytest.mark.parametrize(
    "requirement_line",
    [
        f"{(FIXTURES / 'artifacts/demo-0.0.1.tar.gz').as_posix()}",
        f"{(FIXTURES / 'artifacts/demo-0.0.1-py2.py3-none-any.whl').as_posix()}",
    ],
)
def test_parse_artifact_metadata(requirement_line, project):
    req = parse_requirement(requirement_line)
    candidate = Candidate(req, project.environment)
    assert candidate.get_dependencies_from_metadata() == [
        "idna",
        'chardet; os_name == "nt"',
    ]
    assert candidate.name == "demo"
    assert candidate.version == "0.0.1"


def test_parse_metadata_with_extras(project):
    req = parse_requirement(
        f"demo[tests,security] @ file://"
        f"{(FIXTURES / 'artifacts/demo-0.0.1-py2.py3-none-any.whl').as_posix()}"
    )
    candidate = Candidate(req, project.environment)
    assert candidate.ireq.is_wheel
    assert sorted(candidate.get_dependencies_from_metadata()) == [
        'chardet; os_name == "nt"',
        "idna",
        "pytest",
        'requests; python_version >= "3.6"',
    ]


def test_parse_remote_link_metadata(project):
    req = parse_requirement(
        "http://fixtures.test/artifacts/demo-0.0.1-py2.py3-none-any.whl"
    )
    candidate = Candidate(req, project.environment)
    assert candidate.ireq.is_wheel
    assert candidate.get_dependencies_from_metadata() == [
        "idna",
        'chardet; os_name == "nt"',
    ]
    assert candidate.name == "demo"
    assert candidate.version == "0.0.1"


def test_extras_warning(project, recwarn):
    req = parse_requirement(
        "demo[foo] @ http://fixtures.test/artifacts/demo-0.0.1-py2.py3-none-any.whl"
    )
    candidate = Candidate(req, project.environment)
    assert candidate.ireq.is_wheel
    assert candidate.get_dependencies_from_metadata() == [
        "idna",
        'chardet; os_name == "nt"',
    ]
    warning = recwarn.pop(ExtrasError)
    assert str(warning.message) == "Extras not found: ('foo',)"
    assert candidate.name == "demo"
    assert candidate.version == "0.0.1"


def test_parse_abnormal_specifiers(project):
    req = parse_requirement(
        "http://fixtures.test/artifacts/celery-4.4.2-py2.py3-none-any.whl"
    )
    candidate = Candidate(req, project.environment)
    assert candidate.get_dependencies_from_metadata()
