import pytest
from resolvelib.resolvers import ResolutionImpossible, Resolver

from pdm import termui
from pdm.models.requirements import parse_requirement
from pdm.models.specifiers import PySpecSet
from pdm.resolver import resolve
from pdm.resolver.providers import BaseProvider, EagerUpdateProvider, ReusePinProvider
from pdm.resolver.reporters import SpinnerReporter
from tests import FIXTURES


def resolve_requirements(
    repository,
    lines,
    requires_python="",
    allow_prereleases=None,
    strategy="all",
    preferred_pins=None,
    tracked_names=None,
):
    requirements = []
    for line in lines:
        if line.startswith("-e "):
            requirements.append(parse_requirement(line[3:], True))
        else:
            requirements.append(parse_requirement(line))
    requires_python = PySpecSet(requires_python)
    if not preferred_pins:
        provider = BaseProvider(repository, requires_python, allow_prereleases)
    else:
        provider_class = (
            ReusePinProvider if strategy == "reuse" else EagerUpdateProvider
        )
        provider = provider_class(
            preferred_pins,
            tracked_names or (),
            repository,
            requires_python,
            allow_prereleases,
        )
    ui = termui.UI()
    with ui.open_spinner("Resolving dependencies") as spin, ui.logging("lock"):
        reporter = SpinnerReporter(spin, requirements)
        resolver = Resolver(provider, reporter)
        mapping, *_ = resolve(resolver, requirements, requires_python)
        return mapping


def test_resolve_named_requirement(project, repository):
    result = resolve_requirements(repository, ["requests"])

    assert result["requests"].version == "2.19.1"
    assert result["urllib3"].version == "1.22"
    assert result["chardet"].version == "3.0.4"
    assert result["certifi"].version == "2018.11.17"
    assert result["idna"].version == "2.7"


def test_resolve_requires_python(project, repository):
    result = resolve_requirements(repository, ["django"])
    assert result["django"].version == "1.11.8"
    assert "sqlparse" not in result

    result = resolve_requirements(repository, ["django"], ">=3.6")
    assert result["django"].version == "2.2.9"
    assert "sqlparse" in result

    result = resolve_requirements(repository, ["django; python_version>='3.7'"])
    assert result["django"].version == "2.2.9"
    assert "sqlparse" in result


def test_resolve_allow_prereleases(project, repository):
    repository.add_candidate("foo", "1.0.0")
    repository.add_candidate("foo", "1.1.0-alpha")
    repository.add_candidate("bar", "1.0.0-beta")

    result = resolve_requirements(repository, ["foo"])
    assert result["foo"].version == "1.0.0"

    result = resolve_requirements(repository, ["foo"], allow_prereleases=True)
    assert result["foo"].version == "1.1.0-alpha"

    result = resolve_requirements(repository, ["foo==1.1.0-alpha"])
    assert result["foo"].version == "1.1.0-alpha"

    result = resolve_requirements(repository, ["bar"])
    assert result["bar"].version == "1.0.0-beta"

    with pytest.raises(Exception):
        resolve_requirements(repository, ["bar"], allow_prereleases=False)


def test_resolve_with_extras(project, repository):

    result = resolve_requirements(repository, ["requests[socks]"])
    assert result["pysocks"].version == "1.5.6"


@pytest.mark.parametrize(
    "requirement_line",
    [
        f"{(FIXTURES / 'artifacts/demo-0.0.1.tar.gz').as_posix()}",
        f"{(FIXTURES / 'artifacts/demo-0.0.1-py2.py3-none-any.whl').as_posix()}",
    ],
)
def test_resolve_local_artifacts(project, repository, requirement_line):
    result = resolve_requirements(repository, [requirement_line])
    assert result["idna"].version == "2.7"


@pytest.mark.parametrize(
    "line",
    [
        (FIXTURES / "projects/demo").as_posix(),
        "git+https://github.com/test-root/demo.git#egg=demo",
    ],
)
def test_resolve_vcs_and_local_requirements(
    project, repository, line, is_editable, vcs
):
    editable = "-e " if is_editable else ""
    result = resolve_requirements(repository, [editable + line])
    assert result["idna"].version == "2.7"


def test_resolve_local_and_named_requirement(project, repository, vcs):
    requirements = ["demo", "git+https://github.com/test-root/demo.git#egg=demo"]
    result = resolve_requirements(repository, requirements, ">=3.6")
    assert result["demo"].req.repo == "https://github.com/test-root/demo.git"

    requirements = ["git+https://github.com/test-root/demo.git#egg=demo", "demo"]
    result = resolve_requirements(repository, requirements, ">=3.6")
    assert result["demo"].req.repo == "https://github.com/test-root/demo.git"


def test_resolving_auto_avoid_conflicts(project, repository):
    repository.add_candidate("foo", "0.1.0")
    repository.add_candidate("foo", "0.2.0")
    repository.add_dependencies("foo", "0.1.0", ["hoho<2.0"])
    repository.add_dependencies("foo", "0.2.0", ["hoho>=2.0"])
    repository.add_candidate("bar", "0.1.0")
    repository.add_dependencies("bar", "0.1.0", ["hoho~=1.1"])
    repository.add_candidate("hoho", "2.1")
    repository.add_candidate("hoho", "1.5")

    result = resolve_requirements(repository, ["foo", "bar"])
    assert result["foo"].version == "0.1.0"
    assert result["bar"].version == "0.1.0"
    assert result["hoho"].version == "1.5"


def test_resolve_conflicting_dependencies(project, repository):
    repository.add_candidate("foo", "0.1.0")
    repository.add_dependencies("foo", "0.1.0", ["hoho>=2.0"])
    repository.add_candidate("bar", "0.1.0")
    repository.add_dependencies("bar", "0.1.0", ["hoho~=1.1"])
    repository.add_candidate("hoho", "2.1")
    repository.add_candidate("hoho", "1.5")
    with pytest.raises(ResolutionImpossible):
        resolve_requirements(repository, ["foo", "bar"])


def test_resolve_no_available_versions(project, repository):
    repository.add_candidate("foo", "0.1.0")
    with pytest.raises(ResolutionImpossible):
        resolve_requirements(repository, ["foo>=0.2.0"])


def test_exclude_incompatible_requirements(project, repository):
    repository.add_candidate("foo", "0.1.0")
    repository.add_dependencies("foo", "0.1.0", ["bar; python_version < '3'"])
    result = resolve_requirements(repository, ["foo"], ">=3.6")
    assert "bar" not in result


def test_union_markers_from_different_parents(project, repository):
    repository.add_candidate("foo", "0.1.0")
    repository.add_dependencies("foo", "0.1.0", ["bar; python_version < '3'"])
    repository.add_candidate("bar", "0.1.0")
    result = resolve_requirements(repository, ["foo", "bar"], ">=3.6")
    assert not result["bar"].requires_python


def test_requirements_from_different_sections(project, repository):
    repository.add_candidate("foo", "0.1.0")
    repository.add_candidate("foo", "0.2.0")
    requirements = ["foo", "foo<0.2.0"]
    result = resolve_requirements(repository, requirements)
    assert result["foo"].version == "0.1.0"


def test_resolve_two_extras_from_the_same_package(project, repository):
    # Case borrowed from pypa/pip#7096
    line = (FIXTURES / "projects/demo_extras").as_posix() + "[extra1,extra2]"
    result = resolve_requirements(repository, [line])
    assert "pysocks" in result
    assert "pyopenssl" in result


def test_resolve_package_with_dummy_upbound(project, repository):
    repository.add_candidate("foo", "0.1.0", ">=3.5,<4.0")
    result = resolve_requirements(repository, ["foo"], ">=3.5")
    assert "foo" in result


def test_resolve_dependency_with_extra_marker(project, repository):
    repository.add_candidate("foo", "0.1.0")
    repository.add_dependencies("foo", "0.1.0", ["pytz; extra=='tz' or extra=='all'"])
    result = resolve_requirements(repository, ["foo"])
    assert "pytz" not in result

    result = resolve_requirements(repository, ["foo[tz]"])
    assert "pytz" in result


def test_resolve_parent_from_multiple_sources(project, repository):
    repository.add_candidate("foo", "0.1.0")
    repository.add_dependencies("foo", "0.1.0", ["django"])
    repository.add_candidate("bar", "0.1.0")
    repository.add_dependencies("bar", "0.1.0", ["django"])
    result = resolve_requirements(
        repository, ["foo; python_version ~= '3.8'", "bar"], ">=3.6"
    )
    assert not result["pytz"].marker


def test_resolve_circular_dependencies(project, repository):
    repository.add_candidate("foo", "0.1.0")
    repository.add_dependencies("foo", "0.1.0", ["foobar"])
    repository.add_candidate("foobar", "0.2.0")
    repository.add_dependencies("foobar", "0.2.0", ["foo"])
    result = resolve_requirements(repository, ["foo"])
    assert result["foo"].version == "0.1.0"
    assert result["foo"].sections == ["default"]
    assert result["foobar"].version == "0.2.0"
    assert result["foobar"].sections == ["default"]
