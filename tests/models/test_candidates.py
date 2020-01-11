import pytest

from pdm.exceptions import ExtrasError
from pdm.models.candidates import Candidate
from pdm.models.requirements import Requirement
from tests import FIXTURES


@pytest.mark.parametrize(
    "requirement_line",
    [
        f"{(FIXTURES / 'projects/demo').as_posix()}",
        f"-e {(FIXTURES / 'projects/demo').as_posix()}",
    ],
)
def test_parse_directory_metadata(requirement_line, project, repository):
    req = Requirement.from_line(requirement_line)
    candidate = Candidate(req, repository)
    candidate.prepare_source()
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
def test_parse_artifact_metadata(requirement_line, project, repository):
    req = Requirement.from_line(requirement_line)
    candidate = Candidate(req, repository)
    candidate.prepare_source()
    assert candidate.get_dependencies_from_metadata() == [
        "idna",
        'chardet; os_name == "nt"',
    ]
    assert candidate.name == "demo"
    assert candidate.version == "0.0.1"


def test_parse_metadata_with_extras(project, repository):
    req = Requirement.from_line(
        f"demo[tests,security] @ file://"
        f"{(FIXTURES / 'artifacts/demo-0.0.1-py2.py3-none-any.whl').as_posix()}"
    )
    candidate = Candidate(req, repository)
    assert candidate.is_wheel
    candidate.prepare_source()
    assert sorted(candidate.get_dependencies_from_metadata()) == [
        'chardet; os_name == "nt"',
        "idna",
        "pytest",
        'requests; python_version >= "3.6"',
    ]


def test_parse_remote_link_metadata(project, repository):
    req = Requirement.from_line(
        f"http://fixtures.test/artifacts/demo-0.0.1-py2.py3-none-any.whl"
    )
    candidate = Candidate(req, repository)
    assert candidate.is_wheel
    candidate.prepare_source()
    assert candidate.get_dependencies_from_metadata() == [
        "idna",
        'chardet; os_name == "nt"',
    ]
    assert candidate.name == "demo"
    assert candidate.version == "0.0.1"


def test_extras_warning(project, repository, recwarn):
    req = Requirement.from_line(
        f"demo[foo] @ http://fixtures.test/artifacts/demo-0.0.1-py2.py3-none-any.whl"
    )
    candidate = Candidate(req, repository)
    assert candidate.is_wheel
    candidate.prepare_source()
    assert candidate.get_dependencies_from_metadata() == [
        "idna",
        'chardet; os_name == "nt"',
    ]
    warning = recwarn.pop(ExtrasError)
    assert str(warning.message) == "Extras not found: ('foo',)"
    assert candidate.name == "demo"
    assert candidate.version == "0.0.1"
