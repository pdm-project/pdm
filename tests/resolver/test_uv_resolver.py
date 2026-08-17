from textwrap import dedent

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
    assert len(dependencies) == 3, [dep.identify() for dep in dependencies]
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


def test_parse_uv_lock_with_source_url_fallback(project):
    from pdm.resolver.uv import UvResolver

    lock_path = project.root / "uv.lock"
    lock_path.write_text(
        dedent(
            """
            version = 1
            requires-python = ">=3.8"

            [[package]]
            name = "mdformat-py-edu-fr"
            version = "0.1.1"
            source = { url = "http://foss.heptapod.net/py-edu-fr/mdformat-py-edu-fr/-/archive/0.1.1/mdformat-py-edu-fr.tar.gz" }
            sdist = { hash = "sha256:124488d1796a7ad5f98b1365fe00ff3e71846fd1f91d46e54f8b73c0cdbd78a1" }
            """
        ).strip(),
        encoding="utf-8",
    )

    resolver = UvResolver(
        project.environment,
        requirements=[],
        target=project.environment.spec,
        update_strategy="all",
        strategies=set(),
    )
    resolution = resolver._parse_uv_lock(lock_path)
    candidate = next(iter(resolution.packages)).candidate

    assert candidate.req.url == (
        "http://foss.heptapod.net/py-edu-fr/mdformat-py-edu-fr/-/archive/0.1.1/mdformat-py-edu-fr.tar.gz"
    )
    assert candidate.hashes[0] == {
        "url": "http://foss.heptapod.net/py-edu-fr/mdformat-py-edu-fr/-/archive/0.1.1/mdformat-py-edu-fr.tar.gz",
        "file": "mdformat-py-edu-fr.tar.gz",
        "hash": "sha256:124488d1796a7ad5f98b1365fe00ff3e71846fd1f91d46e54f8b73c0cdbd78a1",
    }


def test_parse_uv_lock_with_local_path_wheel(project):
    from pdm.resolver.uv import UvResolver

    lock_path = project.root / "uv.lock"
    lock_path.write_text(
        dedent(
            """
            version = 1
            requires-python = ">=3.8"

            [[package]]
            name = "my-local-pkg"
            version = "0.1.0"
            source = { path = "./wheels/my_local_pkg-0.1.0-py3-none-any.whl" }

            [[package.wheels]]
            filename = "my_local_pkg-0.1.0-py3-none-any.whl"
            hash = "sha256:abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
            """
        ).strip(),
        encoding="utf-8",
    )

    resolver = UvResolver(
        project.environment,
        requirements=[],
        target=project.environment.spec,
        update_strategy="all",
        strategies=set(),
    )
    resolution = resolver._parse_uv_lock(lock_path)
    candidate = next(iter(resolution.packages)).candidate

    assert candidate.req.path is not None
    assert candidate.name == "my-local-pkg"
    assert candidate.hashes[0] == {
        "url": "my_local_pkg-0.1.0-py3-none-any.whl",
        "file": "my_local_pkg-0.1.0-py3-none-any.whl",
        "hash": "sha256:abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
    }


def test_parse_uv_lock_drops_the_placeholder_root(project):
    """A project with no name gets a placeholder in the generated pyproject.toml,
    so uv writes the root entry under that name. It must not become a dependency."""
    from pdm.formats.uv import PLACEHOLDER_NAME
    from pdm.resolver.uv import UvResolver

    project.pyproject._data.get("project", {}).pop("name", None)
    lock_path = project.root / "uv.lock"
    lock_path.write_text(
        dedent(
            f"""
            version = 1
            requires-python = ">=3.8"

            [[package]]
            name = "{PLACEHOLDER_NAME}"
            version = "0.0.0"
            source = {{ virtual = "." }}

            [[package]]
            name = "packaging"
            version = "24.0"
            source = {{ registry = "https://pypi.org/simple" }}
            sdist = {{ url = "https://example.invalid/packaging-24.0.tar.gz", hash = "sha256:abc" }}
            """
        ).strip(),
        encoding="utf-8",
    )

    resolver = UvResolver(
        project.environment,
        requirements=[],
        target=project.environment.spec,
        update_strategy="all",
        strategies=set(),
    )
    resolution = resolver._parse_uv_lock(lock_path)

    names = {p.candidate.name for p in resolution.packages}
    assert names == {"packaging"}, f"the placeholder root leaked into the resolution: {names}"
