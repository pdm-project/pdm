import shutil
from pathlib import Path

import pytest

from pdm.exceptions import ExtrasError
from pdm.models.candidates import Candidate
from pdm.models.pip_shims import Link, path_to_url
from pdm.models.requirements import parse_requirement
from tests import FIXTURES


def test_parse_local_directory_metadata(project, is_editable):
    requirement_line = f"{(FIXTURES / 'projects/demo').as_posix()}"
    req = parse_requirement(requirement_line, is_editable)
    candidate = Candidate(req, project.environment)
    assert candidate.get_dependencies_from_metadata() == [
        "idna",
        'chardet; os_name == "nt"',
    ]
    assert candidate.name == "demo"
    assert candidate.version == "0.0.1"


@pytest.mark.usefixtures("vcs")
def test_parse_vcs_metadata(project, is_editable):
    requirement_line = "git+https://github.com/test-root/demo.git@master#egg=demo"
    req = parse_requirement(requirement_line, is_editable)
    candidate = Candidate(req, project.environment)
    assert candidate.get_dependencies_from_metadata() == [
        "idna",
        'chardet; os_name == "nt"',
    ]
    assert candidate.name == "demo"
    assert candidate.version == "0.0.1"
    lockfile = candidate.as_lockfile_entry()
    assert lockfile["ref"] == "master"
    if is_editable:
        assert "revision" not in lockfile
    else:
        assert lockfile["revision"] == "1234567890abcdef"


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


@pytest.mark.parametrize(
    "req_str",
    [
        "demo @ file:///${PROJECT_ROOT}/tests/fixtures/artifacts"
        "/demo-0.0.1-py2.py3-none-any.whl",
        "demo @ file:///${PROJECT_ROOT}/tests/fixtures/artifacts/demo-0.0.1.tar.gz",
        "demo @ file:///${PROJECT_ROOT}/tests/fixtures/projects/demo",
        "-e ${PROJECT_ROOT}/tests/fixtures/projects/demo",
    ],
)
def test_expand_project_root_in_url(req_str, core):
    project = core.create_project(FIXTURES.parent.parent)
    if req_str.startswith("-e "):
        req = parse_requirement(req_str[3:], True)
    else:
        req = parse_requirement(req_str)
    candidate = Candidate(req, project.environment)
    assert candidate.get_dependencies_from_metadata() == [
        "idna",
        'chardet; os_name == "nt"',
    ]
    lockfile_entry = candidate.as_lockfile_entry()
    if "path" in lockfile_entry:
        assert lockfile_entry["path"].startswith("./")
    else:
        assert "${PROJECT_ROOT}" in lockfile_entry["url"]


def test_parse_project_file_on_build_error(project):
    req = parse_requirement(f"{(FIXTURES / 'projects/demo-failure').as_posix()}")
    candidate = Candidate(req, project.environment)
    assert sorted(candidate.get_dependencies_from_metadata()) == [
        'chardet; os_name == "nt"',
        "idna",
    ]
    assert candidate.name == "demo"
    assert candidate.version == "0.0.1"


def test_parse_project_file_on_build_error_with_extras(project):
    req = parse_requirement(f"{(FIXTURES / 'projects/demo-failure').as_posix()}")
    req.extras = ("security", "tests")
    candidate = Candidate(req, project.environment)
    deps = candidate.get_dependencies_from_metadata()
    assert 'requests; python_version >= "3.6"' in deps
    assert "pytest" in deps
    assert candidate.name == "demo"
    assert candidate.version == "0.0.1"


def test_parse_project_file_on_build_error_no_dep(project):
    req = parse_requirement(f"{(FIXTURES / 'projects/demo-failure-no-dep').as_posix()}")
    candidate = Candidate(req, project.environment)
    assert candidate.get_dependencies_from_metadata() == []
    assert candidate.name == "demo"
    assert candidate.version == "0.0.1"


def test_parse_poetry_project_metadata(project, is_editable):
    req = parse_requirement(
        f"{(FIXTURES / 'projects/poetry-demo').as_posix()}", is_editable
    )
    candidate = Candidate(req, project.environment)
    requests_dep = "requests (<3.0,>=2.6)" if is_editable else "requests<3.0,>=2.6"
    assert candidate.get_dependencies_from_metadata() == [requests_dep]
    assert candidate.name == "poetry-demo"
    assert candidate.version == "0.1.0"


def test_parse_flit_project_metadata(project, is_editable):
    req = parse_requirement(
        f"{(FIXTURES / 'projects/flit-demo').as_posix()}", is_editable
    )
    candidate = Candidate(req, project.environment)
    deps = candidate.get_dependencies_from_metadata()
    requests_dep = "requests (>=2.6)" if is_editable else "requests>=2.6"
    assert requests_dep in deps
    assert 'configparser; python_version == "2.7"' in deps
    assert candidate.name == "pyflit"
    assert candidate.version == "0.1.0"


@pytest.mark.usefixtures("vcs")
def test_vcs_candidate_in_subdirectory(project, is_editable):
    line = (
        "git+https://github.com/test-root/demo-parent-package.git"
        "@master#egg=package-a&subdirectory=package-a"
    )
    req = parse_requirement(line, is_editable)
    candidate = Candidate(req, project.environment)
    assert candidate.get_dependencies_from_metadata() == ["flask"]
    assert candidate.version == "0.1.0"

    line = (
        "git+https://github.com/test-root/demo-parent-package.git"
        "@master#egg=package-b&subdirectory=package-b"
    )
    req = parse_requirement(line, is_editable)
    candidate = Candidate(req, project.environment)
    assert candidate.get_dependencies_from_metadata() == ["django"]
    assert candidate.version == "0.1.0"


def test_sdist_candidate_with_wheel_cache(project, mocker):
    file_link = Link(path_to_url((FIXTURES / "artifacts/demo-0.0.1.tar.gz").as_posix()))
    built_path = (FIXTURES / "artifacts/demo-0.0.1-py2.py3-none-any.whl").as_posix()
    wheel_cache = project.make_wheel_cache()
    cache_path = wheel_cache.get_path_for_link(file_link)
    if not Path(cache_path).exists():
        Path(cache_path).mkdir(parents=True)
    shutil.copy2(built_path, cache_path)
    req = parse_requirement(file_link.url)
    candidate = Candidate(req, project.environment)
    downloader = mocker.patch("pdm.models.pip_shims.unpack_url")
    candidate.prepare(True)
    downloader.assert_not_called()
    assert Path(candidate.wheel) == Path(cache_path) / Path(built_path).name

    candidate.wheel = None
    builder = mocker.patch("pdm.builders.WheelBuilder.build")
    candidate.build()
    builder.assert_not_called()
    assert Path(candidate.wheel) == Path(cache_path) / Path(built_path).name


@pytest.mark.usefixtures("vcs")
def test_cache_vcs_immutable_revision(project):
    req = parse_requirement("git+https://github.com/test-root/demo.git@master#egg=demo")
    candidate = Candidate(req, project.environment)
    wheel = candidate.build()
    with pytest.raises(ValueError):
        Path(wheel).relative_to(project.cache_dir)
    assert candidate.revision == "1234567890abcdef"

    req = parse_requirement(
        "git+https://github.com/test-root/demo.git@1234567890abcdef#egg=demo"
    )
    candidate = Candidate(req, project.environment)
    wheel = candidate.build()
    assert Path(wheel).relative_to(project.cache_dir)
    assert candidate.revision == "1234567890abcdef"

    # test the revision can be got correctly after cached
    candidate = Candidate(req, project.environment)
    wheel = candidate.prepare(True)
    assert not candidate.source_dir
    assert candidate.revision == "1234567890abcdef"


def test_cache_egg_info_sdist(project):
    req = parse_requirement("demo @ http://fixtures.test/artifacts/demo-0.0.1.tar.gz")
    candidate = Candidate(req, project.environment)
    wheel = candidate.build()
    assert Path(wheel).relative_to(project.cache_dir)


def test_invalidate_incompatible_wheel_link(project, index):
    req = parse_requirement("demo")
    candidate = Candidate(req, project.environment, name="demo", version="0.0.1")
    candidate.prepare(True)
    assert (
        Path(candidate.wheel).name
        == candidate.link.filename
        == "demo-0.0.1-cp36-cp36m-win_amd64.whl"
    )

    candidate.prepare()
    assert (
        Path(candidate.wheel).name
        == candidate.link.filename
        == "demo-0.0.1-py2.py3-none-any.whl"
    )


def test_legacy_pep345_tag_link(project, index):
    req = parse_requirement("pep345-legacy")
    candidate = Candidate(req, project.environment)
    try:
        candidate.prepare()
    except Exception:
        pass
    assert candidate.requires_python == ">=3,<4"
