import shutil

import pytest
from unearth import Link

from pdm.exceptions import ExtrasWarning
from pdm.models.candidates import Candidate
from pdm.models.requirements import parse_requirement
from pdm.utils import path_to_url
from tests import FIXTURES


@pytest.mark.usefixtures("local_finder")
def test_parse_local_directory_metadata(project, is_editable):
    requirement_line = f"{(FIXTURES / 'projects/demo').as_posix()}"
    req = parse_requirement(requirement_line, is_editable)
    candidate = Candidate(req)
    assert candidate.prepare(project.environment).get_dependencies_from_metadata() == [
        "idna",
        'chardet; os_name == "nt"',
    ]
    assert candidate.name == "demo"
    assert candidate.version == "0.0.1"


@pytest.mark.usefixtures("vcs", "local_finder")
def test_parse_vcs_metadata(project, is_editable):
    requirement_line = "git+https://github.com/test-root/demo.git@master#egg=demo"
    req = parse_requirement(requirement_line, is_editable)
    candidate = Candidate(req)
    assert candidate.prepare(project.environment).get_dependencies_from_metadata() == [
        "idna",
        'chardet; os_name == "nt"',
    ]
    assert candidate.name == "demo"
    assert candidate.version == "0.0.1"
    lockfile = candidate.as_lockfile_entry(project.root)
    assert lockfile["ref"] == "master"
    if is_editable:
        assert "revision" not in lockfile
    else:
        assert lockfile["revision"] == "1234567890abcdef"


@pytest.mark.usefixtures("local_finder")
@pytest.mark.parametrize(
    "requirement_line",
    [
        f"{(FIXTURES / 'artifacts/demo-0.0.1.tar.gz').as_posix()}",
        f"{(FIXTURES / 'artifacts/demo-0.0.1-py2.py3-none-any.whl').as_posix()}",
    ],
)
def test_parse_artifact_metadata(requirement_line, project):
    req = parse_requirement(requirement_line)
    candidate = Candidate(req)
    assert candidate.prepare(project.environment).get_dependencies_from_metadata() == [
        "idna",
        'chardet; os_name == "nt"',
    ]
    assert candidate.name == "demo"
    assert candidate.version == "0.0.1"


@pytest.mark.usefixtures("local_finder")
def test_parse_metadata_with_extras(project):
    req = parse_requirement(
        f"demo[tests,security] @ file://{(FIXTURES / 'artifacts/demo-0.0.1-py2.py3-none-any.whl').as_posix()}"
    )
    candidate = Candidate(req)
    prepared = candidate.prepare(project.environment)
    assert prepared.link.is_wheel
    assert sorted(prepared.get_dependencies_from_metadata()) == [
        "pytest",
        'requests; python_version >= "3.6"',
    ]


@pytest.mark.usefixtures("local_finder")
def test_parse_remote_link_metadata(project):
    req = parse_requirement("http://fixtures.test/artifacts/demo-0.0.1-py2.py3-none-any.whl")
    candidate = Candidate(req)
    prepared = candidate.prepare(project.environment)
    assert prepared.link.is_wheel
    assert prepared.get_dependencies_from_metadata() == [
        "idna",
        'chardet; os_name == "nt"',
    ]
    assert candidate.name == "demo"
    assert candidate.version == "0.0.1"


@pytest.mark.usefixtures("local_finder")
def test_extras_warning(project, recwarn):
    req = parse_requirement("demo[foo] @ http://fixtures.test/artifacts/demo-0.0.1-py2.py3-none-any.whl")
    candidate = Candidate(req)
    prepared = candidate.prepare(project.environment)
    assert prepared.link.is_wheel
    assert prepared.get_dependencies_from_metadata() == []
    warning = recwarn.pop(ExtrasWarning)
    assert str(warning.message) == "Extras not found for demo: [foo]"
    assert candidate.name == "demo"
    assert candidate.version == "0.0.1"


@pytest.mark.usefixtures("local_finder")
def test_parse_abnormal_specifiers(project):
    req = parse_requirement("http://fixtures.test/artifacts/celery-4.4.2-py2.py3-none-any.whl")
    candidate = Candidate(req)
    assert candidate.prepare(project.environment).get_dependencies_from_metadata()


@pytest.mark.usefixtures("local_finder")
@pytest.mark.parametrize(
    "req_str",
    [
        "demo @ file:///${PROJECT_ROOT}/tests/fixtures/artifacts/demo-0.0.1-py2.py3-none-any.whl",
        "demo @ file:///${PROJECT_ROOT}/tests/fixtures/artifacts/demo-0.0.1.tar.gz",
        "demo @ file:///${PROJECT_ROOT}/tests/fixtures/projects/demo",
        "-e ./tests/fixtures/projects/demo",
        "-e file:///${PROJECT_ROOT}/tests/fixtures/projects/demo#egg=demo",
        "-e file:///${PROJECT_ROOT}/tests/fixtures/projects/demo-#-with-hash#egg=demo",
    ],
)
def test_expand_project_root_in_url(req_str, core):
    project = core.create_project(FIXTURES.parent.parent)
    if req_str.startswith("-e "):
        req = parse_requirement(req_str[3:], True)
    else:
        req = parse_requirement(req_str)
    req.relocate(project.backend)
    candidate = Candidate(req)
    assert candidate.prepare(project.environment).get_dependencies_from_metadata() == [
        "idna",
        'chardet; os_name == "nt"',
    ]
    lockfile_entry = candidate.as_lockfile_entry(project.root)
    if "path" in lockfile_entry:
        assert lockfile_entry["path"].startswith("./")
    else:
        assert "${PROJECT_ROOT}" in lockfile_entry["url"]


@pytest.mark.usefixtures("local_finder")
def test_parse_project_file_on_build_error(project):
    req = parse_requirement(f"{(FIXTURES / 'projects/demo-failure').as_posix()}")
    candidate = Candidate(req)
    assert sorted(candidate.prepare(project.environment).get_dependencies_from_metadata()) == [
        'chardet; os_name == "nt"',
        "idna",
    ]
    assert candidate.name == "demo"
    assert candidate.version == "0.0.1"


@pytest.mark.usefixtures("local_finder")
def test_parse_project_file_on_build_error_with_extras(project):
    req = parse_requirement(f"{(FIXTURES / 'projects/demo-failure').as_posix()}")
    req.extras = ("security", "tests")
    candidate = Candidate(req)
    deps = candidate.prepare(project.environment).get_dependencies_from_metadata()
    assert 'requests; python_version >= "3.6"' in deps
    assert "pytest" in deps
    assert candidate.name == "demo"
    assert candidate.version == "0.0.1"


@pytest.mark.usefixtures("local_finder")
def test_parse_project_file_on_build_error_no_dep(project):
    req = parse_requirement(f"{(FIXTURES / 'projects/demo-failure-no-dep').as_posix()}")
    candidate = Candidate(req)
    assert candidate.prepare(project.environment).get_dependencies_from_metadata() == []
    assert candidate.name == "demo"
    assert candidate.version == "0.0.1"


@pytest.mark.usefixtures("local_finder")
def test_parse_poetry_project_metadata(project, is_editable):
    req = parse_requirement(f"{(FIXTURES / 'projects/poetry-demo').as_posix()}", is_editable)
    candidate = Candidate(req)
    requests_dep = "requests<3.0,>=2.6"
    assert candidate.prepare(project.environment).get_dependencies_from_metadata() == [requests_dep]
    assert candidate.name == "poetry-demo"
    assert candidate.version == "0.1.0"


@pytest.mark.usefixtures("local_finder")
def test_parse_flit_project_metadata(project, is_editable):
    req = parse_requirement(f"{(FIXTURES / 'projects/flit-demo').as_posix()}", is_editable)
    candidate = Candidate(req)
    deps = candidate.prepare(project.environment).get_dependencies_from_metadata()
    requests_dep = "requests>=2.6"
    assert requests_dep in deps
    assert 'configparser; python_version == "2.7"' in deps
    assert candidate.name == "pyflit"
    assert candidate.version == "0.1.0"


@pytest.mark.usefixtures("vcs", "local_finder")
def test_vcs_candidate_in_subdirectory(project, is_editable):
    line = "git+https://github.com/test-root/demo-parent-package.git@master#egg=package-a&subdirectory=package-a"
    req = parse_requirement(line, is_editable)
    candidate = Candidate(req)
    assert candidate.prepare(project.environment).get_dependencies_from_metadata() == ["flask"]
    assert candidate.version == "0.1.0"

    line = "git+https://github.com/test-root/demo-parent-package.git@master#egg=package-b&subdirectory=package-b"
    req = parse_requirement(line, is_editable)
    candidate = Candidate(req)
    expected_deps = ["django"]
    assert candidate.prepare(project.environment).get_dependencies_from_metadata() == expected_deps
    assert candidate.version == "0.1.0"


@pytest.mark.usefixtures("local_finder")
def test_sdist_candidate_with_wheel_cache(project, mocker):
    file_link = Link(path_to_url((FIXTURES / "artifacts/demo-0.0.1.tar.gz").as_posix()))
    built_path = FIXTURES / "artifacts/demo-0.0.1-py2.py3-none-any.whl"
    wheel_cache = project.make_wheel_cache()
    cache_path = wheel_cache.get_path_for_link(file_link, project.environment.target_python)
    if not cache_path.exists():
        cache_path.mkdir(parents=True)
    shutil.copy2(built_path, cache_path)
    req = parse_requirement(file_link.url)
    downloader = mocker.patch("unearth.finder.unpack_link")
    prepared = Candidate(req).prepare(project.environment)
    prepared.metadata
    downloader.assert_not_called()
    assert prepared.wheel == cache_path / built_path.name

    prepared.wheel = None
    builder = mocker.patch("pdm.builders.WheelBuilder.build")
    wheel = prepared.build()
    builder.assert_not_called()
    assert wheel == cache_path / built_path.name


@pytest.mark.usefixtures("vcs", "local_finder")
def test_cache_vcs_immutable_revision(project):
    req = parse_requirement("git+https://github.com/test-root/demo.git@master#egg=demo")
    candidate = Candidate(req)
    wheel = candidate.prepare(project.environment).build()
    with pytest.raises(ValueError):
        wheel.relative_to(project.cache_dir)
    assert candidate.get_revision() == "1234567890abcdef"

    req = parse_requirement("git+https://github.com/test-root/demo.git@1234567890abcdef#egg=demo")
    candidate = Candidate(req)
    wheel = candidate.prepare(project.environment).build()
    assert wheel.relative_to(project.cache_dir)
    assert candidate.get_revision() == "1234567890abcdef"

    # test the revision can be got correctly after cached
    prepared = Candidate(req).prepare(project.environment)
    assert not prepared._source_dir
    assert prepared.revision == "1234567890abcdef"


@pytest.mark.usefixtures("local_finder")
def test_cache_egg_info_sdist(project):
    req = parse_requirement("demo @ http://fixtures.test/artifacts/demo-0.0.1.tar.gz")
    candidate = Candidate(req)
    wheel = candidate.prepare(project.environment).build()
    assert wheel.relative_to(project.cache_dir)


def test_invalidate_incompatible_wheel_link(project):
    project.project_config["pypi.url"] = "https://my.pypi.org/simple"
    req = parse_requirement("demo")
    prepared = Candidate(
        req,
        name="demo",
        version="0.0.1",
        link=Link("http://fixtures.test/artifacts/demo-0.0.1-cp36-cp36m-win_amd64.whl"),
    ).prepare(project.environment)
    prepared.obtain(True)
    assert prepared.wheel.name == prepared.link.filename == "demo-0.0.1-cp36-cp36m-win_amd64.whl"

    prepared.obtain(False)
    assert prepared.wheel.name == prepared.link.filename == "demo-0.0.1-py2.py3-none-any.whl"


def test_legacy_pep345_tag_link(project):
    project.project_config["pypi.url"] = "https://my.pypi.org/simple"
    req = parse_requirement("pep345-legacy")
    repo = project.get_repository()
    candidate = next(iter(repo.find_candidates(req)))
    assert candidate.requires_python == ">=3,<4"


def test_ignore_invalid_py_version(project):
    project.project_config["pypi.url"] = "https://my.pypi.org/simple"
    req = parse_requirement("wheel")
    repo = project.get_repository()
    candidate = next(iter(repo.find_candidates(req)))
    assert not candidate.requires_python


def test_find_candidates_from_find_links(project):
    repo = project.get_repository()
    repo.sources = [
        {
            "url": "http://fixtures.test/index/demo.html",
            "verify_ssl": False,
            "type": "find_links",
        }
    ]
    candidates = list(repo.find_candidates(parse_requirement("demo")))
    assert len(candidates) == 2


def test_parse_metadata_from_pep621(project, mocker):
    builder = mocker.patch("pdm.builders.wheel.WheelBuilder.build")
    req = parse_requirement(f"test-hatch @ file://{FIXTURES.as_posix()}/projects/test-hatch-static")
    candidate = Candidate(req)
    distribution = candidate.prepare(project.environment).metadata
    assert sorted(distribution.requires) == ["click", "requests"]
    assert distribution.metadata["Summary"] == "Test hatch project"
    builder.assert_not_called()


def test_parse_metadata_with_dynamic_fields(project, local_finder):
    req = parse_requirement(f"demo-package @ file://{FIXTURES.as_posix()}/projects/demo-src-package")
    candidate = Candidate(req)
    metadata = candidate.prepare(project.environment).metadata
    assert not metadata.requires
    assert metadata.version == "0.1.0"
