import shutil
from argparse import Namespace

import pytest

from pdm.formats import MetaConvertError, flit, pipfile, poetry, requirements, setup_py
from pdm.models.requirements import parse_requirement
from pdm.utils import cd
from tests import FIXTURES


def ns(**kwargs):
    default_options = {
        "dev": False,
        "group": None,
        "expandvars": False,
        "self": False,
        "editable_self": False,
        "hashes": True,
    }
    kwargs = {**default_options, **kwargs}
    self = kwargs.pop("self")
    rv = Namespace(**kwargs)
    rv.self = self
    return rv


def test_convert_pipfile(project):
    golden_file = FIXTURES / "Pipfile"
    assert pipfile.check_fingerprint(project, golden_file)
    result, settings = pipfile.convert(project, golden_file, None)

    assert settings["resolution"]["allow-prereleases"]
    assert result["requires-python"] == ">=3.6"

    assert not settings.get("dev-dependencies", {}).get("dev")

    assert "requests" in result["dependencies"]
    assert 'pywinusb; sys_platform == "win32"' in result["dependencies"]

    assert settings["source"][0]["url"] == "https://pypi.python.org/simple"


@pytest.mark.parametrize("is_dev", [True, False])
def test_convert_requirements_file(project, is_dev):
    golden_file = FIXTURES / "requirements.txt"
    assert requirements.check_fingerprint(project, golden_file)
    options = ns(dev=is_dev)
    result, settings = requirements.convert(project, golden_file, options)
    group = settings["dev-dependencies"]["dev"] if is_dev else result["dependencies"]
    dev_group = settings["dev-dependencies"]["dev"]

    assert len(settings["source"]) == 2
    assert "webassets==2.0" in group
    assert 'whoosh==2.7.4; sys_platform == "win32"' in group
    assert "-e git+https://github.com/pypa/pip.git@main#egg=pip" in dev_group
    if not is_dev:
        assert "-e git+https://github.com/pypa/pip.git@main#egg=pip" not in group
    assert (
        "pep508-package @ git+https://github.com/techalchemy/test-project.git"
        "@master#subdirectory=parent_folder/pep508-package" in group
    )


def test_convert_requirements_file_without_name(project, vcs):
    req_file = project.root.joinpath("reqs.txt")
    project.root.joinpath("reqs.txt").write_text("git+https://github.com/test-root/demo.git\n")
    assert requirements.check_fingerprint(project, str(req_file))
    result, _ = requirements.convert(project, str(req_file), ns())

    assert result["dependencies"] == ["demo @ git+https://github.com/test-root/demo.git"]


def test_convert_poetry(project):
    golden_file = FIXTURES / "pyproject.toml"
    assert poetry.check_fingerprint(project, golden_file)
    with cd(FIXTURES):
        result, settings = poetry.convert(project, golden_file, ns())

    assert result["authors"] == [
        {
            "name": "Sébastien Eustace",
            "email": "sebastien@eustace.io",
        },
        {
            "name": "Example, Inc.",
            "email": "inc@example.com",
        },
    ]
    assert result["name"] == "poetry"
    assert result["version"] == "1.0.0"
    assert result["license"] == {"text": "MIT"}
    assert "repository" in result["urls"]
    assert result["requires-python"] == "!=3.0.*,!=3.1.*,!=3.2.*,!=3.3.*,<4.0,>=2.7"
    assert 'cleo<1.0.0,>=0.7.6; python_version ~= "2.7"' in result["dependencies"]
    assert 'cachecontrol[filecache]<1.0.0,>=0.12.4; python_version ~= "3.4"' in result["dependencies"]
    assert "babel==2.9.0" in result["dependencies"]
    assert "mysql" in result["optional-dependencies"]
    assert "psycopg2<3.0,>=2.7" in result["optional-dependencies"]["pgsql"]
    assert len(settings["dev-dependencies"]["dev"]) == 2

    assert result["scripts"] == {"poetry": "poetry.console:run"}
    assert result["entry-points"]["blogtool.parsers"] == {".rst": "some_module:SomeClass"}
    build = settings["build"]
    assert build["includes"] == ["lib/my_package", "tests", "CHANGELOG.md"]
    assert build["excludes"] == ["my_package/excluded.py"]


def test_convert_poetry_12(project):
    golden_file = FIXTURES / "poetry-new.toml"
    with cd(FIXTURES):
        result, settings = poetry.convert(project, golden_file, ns())

    assert result["dependencies"] == ["httpx", "pendulum"]
    assert settings["dev-dependencies"]["test"] == ["pytest<7.0.0,>=6.0.0", "pytest-mock"]


def test_convert_flit(project):
    golden_file = FIXTURES / "projects/flit-demo/pyproject.toml"
    assert flit.check_fingerprint(project, golden_file)
    result, settings = flit.convert(project, golden_file, None)

    assert result["name"] == "pyflit"
    assert result["version"] == "0.1.0"
    assert result["description"] == "An awesome flit demo"
    assert "classifiers" in result["dynamic"]
    assert result["authors"][0] == {
        "name": "Thomas Kluyver",
        "email": "thomas@kluyver.me.uk",
    }
    assert result["urls"]["homepage"] == "https://github.com/takluyver/flit"
    assert result["requires-python"] == ">=3.5"
    assert result["readme"] == "README.rst"
    assert result["urls"]["Documentation"] == "https://flit.readthedocs.io/en/latest/"
    assert result["dependencies"] == [
        "requests>=2.6",
        'configparser; python_version == "2.7"',
    ]

    assert result["optional-dependencies"]["test"] == [
        "pytest >=2.7.3",
        "pytest-cov",
    ]

    assert result["scripts"]["flit"] == "flit:main"
    assert result["entry-points"]["pygments.lexers"]["dogelang"] == "dogelang.lexer:DogeLexer"
    build = settings["build"]
    assert build["includes"] == ["doc/"]
    assert build["excludes"] == ["doc/*.html"]


def test_convert_error_preserve_metadata(project):
    pyproject_file = FIXTURES / "poetry-error.toml"
    try:
        poetry.convert(project, pyproject_file, ns())
    except MetaConvertError as e:
        assert e.data["name"] == "test-poetry"
        assert "dependencies: Invalid specifier" in str(e)
    else:
        pytest.fail("Should raise MetaConvertError")


def test_import_requirements_with_group(project):
    golden_file = FIXTURES / "requirements.txt"
    assert requirements.check_fingerprint(project, golden_file)
    result, settings = requirements.convert(project, golden_file, ns(group="test"))

    group = result["optional-dependencies"]["test"]
    dev_group = settings["dev-dependencies"]["dev"]
    assert "webassets==2.0" in group
    assert 'whoosh==2.7.4; sys_platform == "win32"' in group
    assert "-e git+https://github.com/pypa/pip.git@main#egg=pip" not in group
    assert "-e git+https://github.com/pypa/pip.git@main#egg=pip" in dev_group
    assert not result.get("dependencies")


def test_export_requirements_with_self(project):
    result = requirements.export(project, [], ns(self=True, hashes=False))
    assert result.strip().splitlines()[-1] == ".  # this package"


def test_export_requirements_with_editable_self(project):
    result = requirements.export(project, [], ns(editable_self=True, hashes=False))
    assert result.strip().splitlines()[-1] == "-e .  # this package"


def test_keep_env_vars_in_source(project, monkeypatch):
    monkeypatch.setenv("USER", "foo")
    monkeypatch.setenv("PASSWORD", "bar")
    project.pyproject.settings["source"] = [{"url": "https://${USER}:${PASSWORD}@test.pypi.org/simple", "name": "pypi"}]
    result = requirements.export(project, [], ns())
    assert result.strip().splitlines()[-1] == "--index-url https://${USER}:${PASSWORD}@test.pypi.org/simple"


def test_expand_env_vars_in_source(project, monkeypatch):
    monkeypatch.setenv("USER", "foo")
    monkeypatch.setenv("PASSWORD", "bar")
    project.pyproject.settings["source"] = [{"url": "https://foo:bar@test.pypi.org/simple", "name": "pypi"}]
    result = requirements.export(project, [], ns(expandvars=True))
    assert result.strip().splitlines()[-1] == "--index-url https://foo:bar@test.pypi.org/simple"


def test_export_find_links(project, monkeypatch):
    url = "https://storage.googleapis.com/jax-releases/jax_cuda_releases.html"
    project.pyproject.settings["source"] = [{"url": url, "name": "jax", "type": "find_links"}]
    result = requirements.export(project, [], ns())
    assert result.strip().splitlines()[-1] == f"--find-links {url}"


def test_export_replace_project_root(project):
    artifact = FIXTURES / "artifacts/first-2.0.2-py2.py3-none-any.whl"
    shutil.copy2(artifact, project.root)
    with cd(project.root):
        req = parse_requirement(f"./{artifact.name}")
    result = requirements.export(project, [req], ns(hashes=False))
    assert "${PROJECT_ROOT}" not in result


def test_convert_setup_py_project(project):
    golden_file = FIXTURES / "projects/test-setuptools/setup.py"
    assert setup_py.check_fingerprint(project, golden_file)
    result, settings = setup_py.convert(project, golden_file, ns())
    assert result == {
        "name": "mymodule",
        "version": "0.1.0",
        "description": "A test module",
        "keywords": ["one", "two"],
        "readme": "README.md",
        "authors": [{"name": "frostming"}],
        "license": {"text": "MIT"},
        "classifiers": ["Framework :: Django", "Programming Language :: Python :: 3"],
        "requires-python": ">=3.5",
        "dependencies": ['importlib-metadata; python_version<"3.8"', "requests"],
        "scripts": {"mycli": "mymodule:main"},
    }
    assert settings == {"package-dir": "src"}


def test_convert_poetry_project_with_circular_dependency(project):
    parent_file = FIXTURES / "projects/poetry-with-circular-dep/pyproject.toml"
    child_file = FIXTURES / "projects/poetry-with-circular-dep/packages/child/pyproject.toml"

    _, settings = poetry.convert(project, parent_file, ns())
    assert settings["dev-dependencies"]["dev"] == ["child @ file:///${PROJECT_ROOT}/packages/child"]

    _, settings = poetry.convert(project, child_file, ns())
    assert settings["dev-dependencies"]["dev"] == ["parent @ file:///${PROJECT_ROOT}/../.."]
