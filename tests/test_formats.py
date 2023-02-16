import shutil
from argparse import Namespace

from pdm.formats import flit, pipfile, poetry, requirements, setup_py
from pdm.models.requirements import parse_requirement
from pdm.utils import cd
from tests import FIXTURES


def test_convert_pipfile(project):
    golden_file = FIXTURES / "Pipfile"
    assert pipfile.check_fingerprint(project, golden_file)
    result, settings = pipfile.convert(project, golden_file, None)

    assert settings["allow_prereleases"]
    assert result["requires-python"] == ">=3.6"

    assert not settings.get("dev-dependencies", {}).get("dev")

    assert "requests" in result["dependencies"]
    assert 'pywinusb; sys_platform == "win32"' in result["dependencies"]

    assert settings["source"][0]["url"] == "https://pypi.python.org/simple"


def test_convert_requirements_file(project, is_dev):
    golden_file = FIXTURES / "requirements.txt"
    assert requirements.check_fingerprint(project, golden_file)
    options = Namespace(dev=is_dev, group=None)
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
    result, _ = requirements.convert(project, str(req_file), Namespace(dev=False, group=None))

    assert result["dependencies"] == ["git+https://github.com/test-root/demo.git"]


def test_convert_poetry(project):
    golden_file = FIXTURES / "pyproject.toml"
    assert poetry.check_fingerprint(project, golden_file)
    with cd(FIXTURES):
        result, settings = poetry.convert(project, golden_file, Namespace(dev=False, group=None))

    assert result["authors"][0] == {
        "name": "Sébastien Eustace",
        "email": "sebastien@eustace.io",
    }
    assert result["name"] == "poetry"
    assert result["version"] == "1.0.0"
    assert result["license"] == {"text": "MIT"}
    assert "repository" in result["urls"]
    assert result["requires-python"] == ">=2.7,<4.0,!=3.0.*,!=3.1.*,!=3.2.*,!=3.3.*"
    assert 'cleo<1.0.0,>=0.7.6; python_version ~= "2.7"' in result["dependencies"]
    assert (
        'cachecontrol[filecache]<1.0.0,>=0.12.4; python_version >= "3.4" '
        'and python_version < "4.0"' in result["dependencies"]
    )
    assert "babel==2.9.0" in result["dependencies"]
    assert "mysql" in result["optional-dependencies"]
    assert "psycopg2<3.0,>=2.7" in result["optional-dependencies"]["pgsql"]
    assert len(settings["dev-dependencies"]["dev"]) == 2

    assert result["scripts"] == {"poetry": "poetry.console:run"}
    assert result["entry-points"]["blogtool.parsers"] == {".rst": "some_module:SomeClass"}
    build = settings["build"]
    assert build["includes"] == ["lib/my_package", "tests", "CHANGELOG.md"]
    assert build["excludes"] == ["my_package/excluded.py"]


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


def test_import_requirements_with_group(project):
    golden_file = FIXTURES / "requirements.txt"
    assert requirements.check_fingerprint(project, golden_file)
    result, settings = requirements.convert(project, golden_file, Namespace(dev=False, group="test"))

    group = result["optional-dependencies"]["test"]
    dev_group = settings["dev-dependencies"]["dev"]
    assert "webassets==2.0" in group
    assert 'whoosh==2.7.4; sys_platform == "win32"' in group
    assert "-e git+https://github.com/pypa/pip.git@main#egg=pip" not in group
    assert "-e git+https://github.com/pypa/pip.git@main#egg=pip" in dev_group
    assert not result.get("dependencies")


def test_export_expand_env_vars_in_source(project, monkeypatch):
    monkeypatch.setenv("USER", "foo")
    monkeypatch.setenv("PASSWORD", "bar")
    project.pyproject.settings["source"] = [{"url": "https://${USER}:${PASSWORD}@test.pypi.org/simple", "name": "pypi"}]
    result = requirements.export(project, [], Namespace())
    assert result.strip().splitlines()[-1] == "--index-url https://foo:bar@test.pypi.org/simple"


def test_export_replace_project_root(project):
    artifact = FIXTURES / "artifacts/first-2.0.2-py2.py3-none-any.whl"
    shutil.copy2(artifact, project.root)
    with cd(project.root):
        req = parse_requirement(f"./{artifact.name}")
    result = requirements.export(project, [req], Namespace(hashes=False))
    assert "${PROJECT_ROOT}" not in result


def test_convert_setup_py_project(project):
    golden_file = FIXTURES / "projects/test-setuptools/setup.py"
    assert setup_py.check_fingerprint(project, golden_file)
    result, settings = setup_py.convert(project, golden_file, Namespace())
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
