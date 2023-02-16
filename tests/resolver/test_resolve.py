import pytest
from resolvelib.resolvers import ResolutionImpossible, Resolver

from pdm.cli.actions import resolve_candidates_from_lockfile
from pdm.models.requirements import parse_requirement
from pdm.models.specifiers import PySpecSet
from pdm.resolver import resolve as _resolve
from pdm.resolver.reporters import SpinnerReporter
from tests import FIXTURES


@pytest.fixture()
def resolve(project, repository):
    def resolve_func(
        lines,
        requires_python="",
        allow_prereleases=None,
        strategy="all",
        tracked_names=None,
    ):
        repository.environment.python_requires = PySpecSet(requires_python)
        if allow_prereleases is not None:
            project.pyproject.settings["allow_prereleases"] = allow_prereleases
        requirements = []
        for line in lines:
            if line.startswith("-e "):
                requirements.append(parse_requirement(line[3:], True))
            else:
                requirements.append(parse_requirement(line))
        provider = project.get_provider(strategy, tracked_names)

        ui = project.core.ui
        with ui.open_spinner("Resolving dependencies") as spin, ui.logging("lock"):
            reporter = SpinnerReporter(spin, requirements)
            resolver = Resolver(provider, reporter)
            mapping, *_ = _resolve(resolver, requirements, repository.environment.python_requires)
            return mapping

    return resolve_func


def test_resolve_named_requirement(resolve):
    result = resolve(["requests"])

    assert result["requests"].version == "2.19.1"
    assert result["urllib3"].version == "1.22"
    assert result["chardet"].version == "3.0.4"
    assert result["certifi"].version == "2018.11.17"
    assert result["idna"].version == "2.7"


def test_resolve_requires_python(resolve):
    result = resolve(["django"])
    assert result["django"].version == "1.11.8"
    assert "sqlparse" not in result

    result = resolve(["django"], ">=3.6")
    assert result["django"].version == "2.2.9"
    assert "sqlparse" in result

    result = resolve(["django; python_version>='3.7'"])
    assert result["django"].version == "2.2.9"
    assert "sqlparse" in result


def test_resolve_allow_prereleases(resolve, repository):
    repository.add_candidate("foo", "1.0.0")
    repository.add_candidate("foo", "1.1.0-alpha")
    repository.add_candidate("bar", "1.0.0-beta")

    result = resolve(["foo"])
    assert result["foo"].version == "1.0.0"

    result = resolve(["foo"], allow_prereleases=True)
    assert result["foo"].version == "1.1.0-alpha"

    result = resolve(["foo==1.1.0a0"])
    assert result["foo"].version == "1.1.0-alpha"

    result = resolve(["bar"])
    assert result["bar"].version == "1.0.0-beta"

    with pytest.raises(ResolutionImpossible):
        resolve(["bar"], allow_prereleases=False)


def test_resolve_with_extras(resolve):
    result = resolve(["requests[socks]"])
    assert result["pysocks"].version == "1.5.6"


@pytest.mark.parametrize(
    "requirement_line",
    [
        f"{(FIXTURES / 'artifacts/demo-0.0.1.tar.gz').as_posix()}",
        f"{(FIXTURES / 'artifacts/demo-0.0.1-py2.py3-none-any.whl').as_posix()}",
    ],
    ids=["sdist", "wheel"],
)
def test_resolve_local_artifacts(resolve, requirement_line):
    result = resolve([requirement_line], ">=3.6")
    assert result["idna"].version == "2.7"


@pytest.mark.parametrize(
    "line",
    [
        (FIXTURES / "projects/demo").as_posix(),
        "git+https://github.com/test-root/demo.git#egg=demo",
    ],
)
def test_resolve_vcs_and_local_requirements(resolve, line, is_editable, vcs):
    editable = "-e " if is_editable else ""
    result = resolve([editable + line], ">=3.6")
    assert result["idna"].version == "2.7"


def test_resolve_vcs_without_explicit_name(resolve, vcs):
    requirement = "git+https://github.com/test-root/demo.git"
    result = resolve([requirement], ">=3.6")
    assert result["idna"].version == "2.7"


def test_resolve_local_and_named_requirement(resolve, vcs):
    requirements = ["demo", "git+https://github.com/test-root/demo.git#egg=demo"]
    result = resolve(requirements, ">=3.6")
    assert result["demo"].req.is_vcs

    requirements = ["git+https://github.com/test-root/demo.git#egg=demo", "demo"]
    result = resolve(requirements, ">=3.6")
    assert result["demo"].req.is_vcs


def test_resolving_auto_avoid_conflicts(resolve, repository):
    repository.add_candidate("foo", "0.1.0")
    repository.add_candidate("foo", "0.2.0")
    repository.add_dependencies("foo", "0.1.0", ["hoho<2.0"])
    repository.add_dependencies("foo", "0.2.0", ["hoho>=2.0"])
    repository.add_candidate("bar", "0.1.0")
    repository.add_dependencies("bar", "0.1.0", ["hoho~=1.1"])
    repository.add_candidate("hoho", "2.1")
    repository.add_candidate("hoho", "1.5")

    result = resolve(["foo", "bar"])
    assert result["foo"].version == "0.1.0"
    assert result["bar"].version == "0.1.0"
    assert result["hoho"].version == "1.5"


def test_resolve_conflicting_dependencies(resolve, repository):
    repository.add_candidate("foo", "0.1.0")
    repository.add_dependencies("foo", "0.1.0", ["hoho>=2.0"])
    repository.add_candidate("bar", "0.1.0")
    repository.add_dependencies("bar", "0.1.0", ["hoho~=1.1"])
    repository.add_candidate("hoho", "2.1")
    repository.add_candidate("hoho", "1.5")
    with pytest.raises(ResolutionImpossible):
        resolve(["foo", "bar"])


@pytest.mark.parametrize("overrides", ["2.1", ">=1.8", "==2.1"])
def test_resolve_conflicting_dependencies_with_overrides(project, resolve, repository, overrides):
    repository.add_candidate("foo", "0.1.0")
    repository.add_dependencies("foo", "0.1.0", ["hoho>=2.0"])
    repository.add_candidate("bar", "0.1.0")
    repository.add_dependencies("bar", "0.1.0", ["hoho~=1.1"])
    repository.add_candidate("hoho", "2.1")
    repository.add_candidate("hoho", "1.5")
    project.pyproject.settings["resolution"] = {"overrides": {"hoho": overrides}}
    result = resolve(["foo", "bar"])
    assert result["hoho"].version == "2.1"


def test_resolve_no_available_versions(resolve, repository):
    repository.add_candidate("foo", "0.1.0")
    with pytest.raises(ResolutionImpossible):
        resolve(["foo>=0.2.0"])


def test_exclude_incompatible_requirements(resolve, repository):
    repository.add_candidate("foo", "0.1.0")
    repository.add_dependencies("foo", "0.1.0", ["bar; python_version < '3'"])
    result = resolve(["foo"], ">=3.6")
    assert "bar" not in result


def test_union_markers_from_different_parents(resolve, repository):
    repository.add_candidate("foo", "0.1.0")
    repository.add_dependencies("foo", "0.1.0", ["bar; python_version < '3'"])
    repository.add_candidate("bar", "0.1.0")
    result = resolve(["foo", "bar"], ">=3.6")
    assert not result["bar"].requires_python


def test_requirements_from_different_groups(resolve, repository):
    repository.add_candidate("foo", "0.1.0")
    repository.add_candidate("foo", "0.2.0")
    requirements = ["foo", "foo<0.2.0"]
    result = resolve(requirements)
    assert result["foo"].version == "0.1.0"


def test_resolve_two_extras_from_the_same_package(resolve):
    # Case borrowed from pypa/pip#7096
    line = (FIXTURES / "projects/demo_extras").as_posix() + "[extra1,extra2]"
    result = resolve([line])
    assert "pysocks" in result
    assert "pyopenssl" in result


def test_resolve_package_with_dummy_upbound(resolve, repository):
    repository.add_candidate("foo", "0.1.0", ">=3.5,<4.0")
    result = resolve(["foo"], ">=3.5")
    assert "foo" in result


def test_resolve_dependency_with_extra_marker(resolve, repository):
    repository.add_candidate("foo", "0.1.0")
    repository.add_dependencies("foo", "0.1.0", ["pytz; extra=='tz' or extra=='all'"])
    result = resolve(["foo"])
    assert "pytz" not in result

    result = resolve(["foo[tz]"])
    assert "pytz" in result


def test_resolve_circular_dependencies(resolve, repository):
    repository.add_candidate("foo", "0.1.0")
    repository.add_dependencies("foo", "0.1.0", ["foobar"])
    repository.add_candidate("foobar", "0.2.0")
    repository.add_dependencies("foobar", "0.2.0", ["foo"])
    result = resolve(["foo"])
    assert result["foo"].version == "0.1.0"
    assert result["foobar"].version == "0.2.0"


def test_resolve_candidates_to_install(project):
    project.lockfile.set_data(
        {
            "package": [
                {
                    "name": "pytest",
                    "version": "4.6.0",
                    "summary": "pytest module",
                    "dependencies": ["py>=3.0", "configparser; sys_platform=='win32'"],
                },
                {
                    "name": "configparser",
                    "version": "1.2.0",
                    "summary": "configparser module",
                    "dependencies": ["backports"],
                },
                {
                    "name": "py",
                    "version": "3.6.0",
                    "summary": "py module",
                },
                {
                    "name": "backports",
                    "version": "2.2.0",
                    "summary": "backports module",
                },
            ]
        }
    )
    project.environment.marker_environment["sys_platform"] = "linux"
    reqs = [parse_requirement("pytest")]
    result = resolve_candidates_from_lockfile(project, reqs)
    assert result["pytest"].version == "4.6.0"
    assert result["py"].version == "3.6.0"
    assert "configparser" not in result
    assert "backports" not in result

    project.environment.marker_environment["sys_platform"] = "win32"
    result = resolve_candidates_from_lockfile(project, reqs)
    assert result["pytest"].version == "4.6.0"
    assert result["py"].version == "3.6.0"
    assert result["configparser"].version == "1.2.0"
    assert result["backports"].version == "2.2.0"


def test_resolve_prefer_requirement_with_prereleases(resolve):
    result = resolve(["urllib3", "requests>=2.20.0b0"])
    assert result["urllib3"].version == "1.23b0"


def test_resolve_with_python_marker(resolve):
    result = resolve(["demo; python_version>='3.6'"])
    assert result["demo"].version == "0.0.1"


def test_resolve_file_req_with_prerelease(resolve, vcs):
    result = resolve(
        [
            "using-demo==0.1.0",
            "demo @ git+https://github.com/test-root/demo-prerelease.git",
        ],
        ">=3.6",
        allow_prereleases=False,
    )
    assert result["demo"].version == "0.0.2b0"


def test_resolve_extra_requirements_no_break_constraints(resolve, repository):
    repository.add_candidate("foo", "0.1.0")
    repository.add_dependencies("foo", "0.1.0", ["chardet; extra=='chardet'"])
    repository.add_candidate("foo", "0.2.0")
    repository.add_dependencies("foo", "0.2.0", ["chardet; extra=='chardet'"])
    result = resolve(["foo[chardet]<0.2.0"])
    assert "chardet" in result
    assert result["foo"].version == "0.1.0"


def test_resolve_extra_and_underlying_to_the_same_version(resolve, repository):
    repository.add_candidate("foo", "0.1.0")
    repository.add_dependencies("foo", "0.1.0", ["chardet; extra=='enc'"])
    repository.add_candidate("foo", "0.2.0")
    repository.add_dependencies("foo", "0.2.0", ["chardet; extra=='enc'"])
    repository.add_candidate("bar", "0.1.0")
    repository.add_dependencies("bar", "0.1.0", ["foo[enc]>=0.1.0"])
    result = resolve(["foo==0.1.0", "bar"])
    assert result["foo"].version == result["foo[enc]"].version == "0.1.0"
