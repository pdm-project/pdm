import pytest

from pdm.models.markers import EnvSpec
from pdm.models.requirements import parse_requirement

pytestmark = [pytest.mark.network, pytest.mark.uv]


def resolve(environment, requirements, target=None):
    from pdm.resolver.uv import UvResolver

    reqs = []
    for req in requirements:
        if isinstance(req, str):
            req = parse_requirement(req)
            req.groups = ["default"]
        reqs.append(req)

    resolver = UvResolver(
        environment,
        requirements=reqs,
        target=target or environment.spec,
        update_strategy="all",
        strategies=set(),
    )
    return resolver.resolve()


def test_resolve_requirements(project):
    requirements = ["requests==2.32.0", "urllib3<2"]
    resolution = resolve(project.environment, requirements)
    mapping = {p.candidate.identify(): p.candidate for p in resolution.packages}
    assert mapping["requests"].version == "2.32.0"
    assert mapping["urllib3"].version.startswith("1.26")


def test_resolve_vcs_requirement(project):
    requirements = ["git+https://github.com/pallets/click.git@8.1.0"]
    resolution = resolve(project.environment, requirements)
    mapping = {p.candidate.identify(): p.candidate for p in resolution.packages}
    assert "colorama" in mapping
    assert mapping["click"].req.is_vcs


def test_resolve_with_python_requires(project):
    requirements = ["urllib3<2; python_version<'3.10'", "urllib3>=2; python_version>='3.10'"]
    if project.python.version_tuple >= (3, 10):
        resolution = resolve(project.environment, requirements, EnvSpec.from_spec(">=3.10"))
        packages = list(resolution.packages)
        assert len(packages) == 1
        assert packages[0].candidate.version.startswith("2.")

    resolution = resolve(project.environment, requirements, EnvSpec.from_spec(">=3.8"))
    packages = list(resolution.packages)
    assert len(packages) == 2


def test_resolve_dependencies_with_nested_extras(project):
    name = project.name
    project.add_dependencies(["urllib3"], "default", write=False)
    project.add_dependencies(["idna"], "extra1", write=False)
    project.add_dependencies(["chardet", f"{name}[extra1]"], "extra2", write=False)
    project.add_dependencies([f"{name}[extra1,extra2]"], "all")

    dependencies = [*project.get_dependencies(), *project.get_dependencies("all")]
    assert len(dependencies) == 4
    resolution = resolve(project.environment, dependencies)
    assert resolution.collected_groups == {"default", "extra1", "extra2", "all"}
    mapping = {p.candidate.identify(): p.candidate for p in resolution.packages}
    assert set(mapping) == {"urllib3", "idna", "chardet"}


@pytest.mark.parametrize("overrides", ("2.31.0", "==2.31.0"))
def test_resolve_dependencies_with_overrides(project, overrides):
    requirements = ["requests==2.32.0"]

    project.pyproject.settings["resolution"] = {"overrides": {"requests": overrides}}

    resolution = resolve(project.environment, requirements)

    mapping = {p.candidate.identify(): p.candidate for p in resolution.packages}
    assert mapping["requests"].version == "2.31.0"
