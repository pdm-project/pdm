import os

import pytest

from pdm.models.markers import EnvSpec
from pdm.models.requirements import parse_requirement
from tests.test_installer import environment


pytestmark = [pytest.mark.network, pytest.mark.uv]


def get_resolver(environment, requirements, target=None):
    from pdm.resolver.uv import UvResolver

    resolver = UvResolver(
        environment,
        requirements=requirements,
        target=target or environment.spec,
        update_strategy="all",
        strategies=set(),
    )

    return resolver


def resolve(environment, requirements, target=None):

    reqs = []
    for req in requirements:
        if isinstance(req, str):
            req = parse_requirement(req)
            req.groups = ["default"]
        reqs.append(req)
    resolver = get_resolver(environment, reqs, target)
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


def test_index_strategy(project, monkeypatch):
    from pdm.resolver.uv import ALLOWED_INDEX_STRATEGIES

    environment = project.environment
    resolver = get_resolver(environment, [], None)

    command = resolver._build_lock_command()
    assert "--index-strategy=unsafe-best-match" in command

    project.pyproject.settings["resolution"] = {"respect-source-order": True}
    command = resolver._build_lock_command()
    assert "--index-strategy=unsafe-first-match" in command

    for index_strategy in ALLOWED_INDEX_STRATEGIES:
        monkeypatch.setenv("UV_INDEX_STRATEGY", index_strategy)
        command = resolver._build_lock_command()
        assert r"--index-strategy={strategy}" in command

    with pytest.raises(ValueError):
        monkeypatch.setenv("UV_INDEX_STRATEGY", "abcd")
        command = resolver._build_lock_command()
