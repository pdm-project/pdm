import pytest
from resolvelib.resolvers import ResolutionImpossible

from pdm.cli.actions import resolve_candidates_from_lockfile
from pdm.exceptions import PackageWarning
from pdm.models.markers import EnvSpec
from pdm.models.requirements import parse_requirement
from pdm.models.specifiers import PySpecSet
from pdm.project.lockfile import FLAG_DIRECT_MINIMAL_VERSIONS, FLAG_INHERIT_METADATA
from pdm.resolver.reporters import LockReporter
from tests import FIXTURES


@pytest.fixture()
def resolve(project, repository):
    def resolve_func(
        lines,
        requires_python=None,
        allow_prereleases=None,
        strategy="all",
        tracked_names=None,
        direct_minimal_versions=False,
        inherit_metadata=False,
        platform=None,
    ):
        env_spec = project.environment.allow_all_spec
        replace_dict = {}
        if requires_python:
            replace_dict["requires_python"] = PySpecSet(requires_python)
        if platform:
            replace_dict["platform"] = platform
        env_spec = env_spec.replace(**replace_dict)
        if allow_prereleases is not None:
            project.pyproject.settings.setdefault("resolution", {})["allow-prereleases"] = allow_prereleases
        requirements = []
        for line in lines:
            if line.startswith("-e "):
                requirements.append(parse_requirement(line[3:], True))
            else:
                requirements.append(parse_requirement(line))

        ui = project.core.ui
        strategies = project.lockfile.default_strategies.copy()
        if inherit_metadata:
            strategies.add(FLAG_INHERIT_METADATA)
        if direct_minimal_versions:
            strategies.add(FLAG_DIRECT_MINIMAL_VERSIONS)

        with ui.logging("lock"):
            resolver = project.get_resolver()(
                environment=project.environment,
                requirements=requirements,
                update_strategy=strategy,
                strategies=strategies,
                target=env_spec,
                tracked_names=tracked_names,
                reporter=LockReporter(),
            )
            return resolver.resolve().candidates

    return resolve_func


def test_resolve_named_requirement(resolve):
    result = resolve(["requests"])

    assert result["requests"].version == "2.19.1"
    assert result["urllib3"].version == "1.22"
    assert result["chardet"].version == "3.0.4"
    assert result["certifi"].version == "2018.11.17"
    assert result["idna"].version == "2.7"


def test_resolve_exclude(resolve, project):
    project.pyproject.settings.setdefault("resolution", {})["excludes"] = ["urllib3"]
    result = resolve(["requests"])

    assert result["requests"].version == "2.19.1"
    assert result["chardet"].version == "3.0.4"
    assert result["certifi"].version == "2018.11.17"
    assert result["idna"].version == "2.7"
    assert "urllib3" not in result


def test_resolve_requires_python(resolve, project):
    project.environment.python_requires = PySpecSet(">=2.7")
    with pytest.warns(PackageWarning) as records:
        result = resolve(["django"])
    assert len(records) > 0
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
    assert result["urllib3"].version == "1.22"
    assert result["chardet"].version == "3.0.4"
    assert result["certifi"].version == "2018.11.17"
    assert result["idna"].version == "2.7"
    assert result["requests"].version == "2.19.1"


def test_resolve_with_extras_and_excludes(resolve, project):
    project.pyproject.settings.setdefault("resolution", {})["excludes"] = ["requests"]
    result = resolve(["requests[socks]"])
    assert result["pysocks"].version == "1.5.6"
    assert "requests" not in result
    assert "urllib3" not in result


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
    repository.add_candidate("baz", "0.1.0")
    repository.add_dependencies("baz", "0.1.0", ["hoho[extra]~=1.1"])
    repository.add_candidate("hoho", "2.1")
    repository.add_candidate("hoho", "1.5")
    project.pyproject.settings["resolution"] = {"overrides": {"hoho": overrides}}
    result = resolve(["foo", "bar"])
    assert result["hoho"].version == "2.1"
    result = resolve(["foo", "baz"])
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
            "metadata": {"strategy": ["cross_platform"]},
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
            ],
        }
    )
    reqs = [parse_requirement("pytest")]
    result = resolve_candidates_from_lockfile(project, reqs, env_spec=EnvSpec.from_spec("==3.11", "linux", "cpython"))
    assert result["pytest"].version == "4.6.0"
    assert result["py"].version == "3.6.0"
    assert "configparser" not in result
    assert "backports" not in result

    result = resolve_candidates_from_lockfile(project, reqs, env_spec=EnvSpec.from_spec("==3.11", "windows", "cpython"))
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


def test_resolve_skip_candidate_with_invalid_metadata(resolve, repository):
    repository.add_candidate("sqlparse", "0.4.0")
    repository.add_dependencies("sqlparse", "0.4.0", ["django>=1.11'"])
    result = resolve(["sqlparse"], ">=3.6")
    assert result["sqlparse"].version == "0.3.0"


def test_resolve_direct_minimal_versions(resolve, repository, project):
    repository.add_candidate("pytz", "2019.6")
    project.add_dependencies(["django"])
    result = resolve(["django"], ">=3.6", direct_minimal_versions=True)
    assert result["django"].version == "1.11.8"
    assert result["pytz"].version == "2019.6"


def test_resolve_record_markers(resolve, repository, project):
    repository.add_candidate("A", "1.0")
    repository.add_candidate("B", "1.0")
    repository.add_candidate("C", "1.0")
    repository.add_candidate("D", "1.0")
    repository.add_candidate("E", "1.0")
    repository.add_candidate("F", "1.0")
    repository.add_dependencies("A", "1.0", ["B; os_name == 'posix'", "C; os_name=='nt'"])
    # package D has transitive markers that conflict
    repository.add_dependencies("C", "1.0", ["D; os_name!='nt'", "E; python_version < '3.8'"])
    # package E has union markers
    repository.add_dependencies("B", "1.0", ["E; python_version >= '3.7'"])
    # B -> E -> F -> B has circular dependency
    repository.add_dependencies("E", "1.0", ["F; platform_machine=='x86_64'"])
    repository.add_dependencies("F", "1.0", ["B"])

    result = resolve(["A"], ">=3.6", inherit_metadata=True)
    assert result["a"].version == "1.0"
    assert "d" not in result
    assert (
        str(result["e"].req.marker)
        == 'python_version >= "3.7" and os_name == "posix" or python_version < "3.8" and os_name == "nt"'
    )
    assert (
        str(result["f"].req.marker)
        == 'python_version >= "3.7" and os_name == "posix" and platform_machine == "x86_64" or '
        'python_version < "3.8" and os_name == "nt" and platform_machine == "x86_64"'
    )
    assert (
        str(result["b"].req.marker) == 'os_name == "posix" or (os_name == "posix" or os_name == "nt") and '
        'platform_machine == "x86_64" and python_version < "3.8"'
    )
