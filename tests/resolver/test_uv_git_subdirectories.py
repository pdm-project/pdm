from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from pdm.compat import tomllib
from pdm.formats.uv import uv_file_builder
from pdm.models.candidates import Candidate
from pdm.models.repositories import LockedRepository, Package
from pdm.models.requirements import parse_requirement
from pdm.resolver.uv import UvResolver

REVISION = "1234567890abcdef1234567890abcdef12345678"
SUBDIRECTORY = "packages/first package"


@pytest.fixture(params=[None, "main", "feature/subdir+test"])
def git_requirement(request):
    ref = f"@{request.param}" if request.param else ""
    req = parse_requirement(f"first @ git+https://example.invalid/repo.git{ref}#subdirectory=packages/first%20package")
    req.revision = REVISION
    req.groups = ["default"]
    return req


def test_uv_pyproject_keeps_git_subdirectory(project, git_requirement):
    repository = LockedRepository({}, project.sources, project.environment)
    with uv_file_builder(project, ">=3.10", [git_requirement], repository) as builder:
        data = tomllib.loads(builder.build_pyproject_toml().read_text())

    source = data["tool"]["uv"]["sources"]["first"]
    assert source["subdirectory"] == SUBDIRECTORY
    assert source["git"] == "https://example.invalid/repo.git"
    assert source.get("rev") == git_requirement.ref


def test_uv_reuse_lock_keeps_git_subdirectory(project, git_requirement):
    repository = LockedRepository({}, project.sources, project.environment)
    repository.add_package(Package(Candidate(git_requirement, name="first", version="1.0"), [], ""))
    with uv_file_builder(project, ">=3.10", [git_requirement], repository) as builder:
        data = tomllib.loads(builder.build_uv_lock().read_text())

    source = next(package["source"]["git"] for package in data["package"] if package["name"] == "first")
    parsed = urlsplit(source)
    expected = {"subdirectory": [SUBDIRECTORY]}
    if git_requirement.ref:
        expected["rev"] = [git_requirement.ref]
    assert parse_qs(parsed.query) == expected
    assert parsed.fragment == REVISION


def test_parse_uv_lock_restores_git_subdirectory(project, git_requirement):
    query = {"subdirectory": SUBDIRECTORY}
    if git_requirement.ref:
        query["rev"] = git_requirement.ref
    url = f"https://example.invalid/repo.git?{urlencode(query)}#{REVISION}"
    lock = project.root / "uv.lock"
    lock.write_text(
        'version = 1\nrequires-python = ">=3.10"\n'
        f'[[package]]\nname = "first"\nversion = "1.0"\nsource = {{ git = "{url}" }}\n'
    )
    resolver = UvResolver(
        project.environment,
        requirements=[],
        target=project.environment.spec,
        update_strategy="all",
        strategies=set(),
    )
    packages = resolver._parse_uv_lock(lock).packages
    req = next(iter(packages)).candidate.req

    assert req.subdirectory == SUBDIRECTORY
    assert req.ref == git_requirement.ref
    assert req.revision == REVISION
    assert req.repo == "https://example.invalid/repo.git"
