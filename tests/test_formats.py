from pdm.formats import flit, pipfile, poetry, requirements
from tests import FIXTURES


def test_convert_pipfile(project):
    golden_file = FIXTURES / "Pipfile"
    assert pipfile.check_fingerprint(project, golden_file)
    result = pipfile.convert(project, golden_file)

    assert result["allow_prereleases"]
    assert result["python_requires"] == ">=3.6"

    assert not result["dev-dependencies"]

    assert result["dependencies"]["requests"] == "*"
    assert result["dependencies"]["pywinusb"]["version"] == "*"
    assert result["dependencies"]["pywinusb"]["marker"] == "sys_platform == 'win32'"

    assert result["source"][0]["url"] == "https://pypi.python.org/simple"


def test_convert_requirements_file(project):
    golden_file = FIXTURES / "requirements.txt"
    assert requirements.check_fingerprint(project, golden_file)
    result = requirements.convert(project, golden_file)

    assert len(result["source"]) == 2
    assert result["dependencies"]["webassets"] == "==2.0"
    assert result["dependencies"]["whoosh"]["marker"] == "sys_platform == 'win32'"
    assert result["dependencies"]["pip"]["editable"]
    assert result["dependencies"]["pip"]["git"] == "https://github.com/pypa/pip.git"


def test_convert_poetry(project):
    golden_file = FIXTURES / "pyproject-poetry.toml"
    assert poetry.check_fingerprint(project, golden_file)
    result = poetry.convert(project, golden_file)

    assert result["author"] == "Sébastien Eustace <sebastien@eustace.io>"
    assert result["name"] == "poetry"
    assert result["version"] == "1.0.0"
    assert "Repository" in result["project_urls"]
    assert result["python_requires"] == ">=2.7,<4.0,!=3.0.*,!=3.1.*,!=3.2.*,!=3.3.*"
    assert result["dependencies"]["cleo"]["marker"] == "python_version ~= '2.7'"
    assert result["dependencies"]["cachecontrol"]["marker"] == (
        "python_version >= '3.4' and python_version < '4.0'"
    )
    assert result["dependencies"]["babel"] == "==2.9.0"
    assert "psycopg2" not in result["dependencies"]
    assert "psycopg2" in result["pgsql-dependencies"]
    assert sorted(result["extras"]) == ["mysql", "pgsql"]
    assert len(result["dev-dependencies"]) == 2

    assert result["cli"] == {"poetry": "poetry.console:run"}
    assert result["entry_points"]["blogtool.parsers"] == {
        ".rst": "some_module:SomeClass"
    }
    assert result["includes"] == ["lib/my_package", "tests", "CHANGELOG.md"]
    assert result["excludes"] == ["my_package/excluded.py"]


def test_convert_flit(project):
    golden_file = FIXTURES / "projects/flit-demo/pyproject.toml"
    assert flit.check_fingerprint(project, golden_file)
    result = flit.convert(project, golden_file)

    assert result["name"] == "pyflit"
    assert result["version"] == "0.1.0"
    assert result["author"] == "Thomas Kluyver <thomas@kluyver.me.uk>"
    assert result["homepage"] == "https://github.com/takluyver/flit"
    assert result["python_requires"] == ">=3.5"
    assert result["readme"] == "README.rst"
    assert (
        result["project_urls"]["Documentation"]
        == "https://flit.readthedocs.io/en/latest/"
    )
    assert result["dependencies"]["requests"] == ">=2.6"
    assert result["dependencies"]["configparser"]["marker"] == "python_version == '2.7'"

    assert sorted(result["extras"]) == ["doc", "test"]
    assert result["test-dependencies"]["pytest"] == ">=2.7.3"

    assert result["cli"]["flit"] == "flit:main"
    assert (
        result["entry_points"]["pygments.lexers"]["dogelang"]
        == "dogelang.lexer:DogeLexer"
    )
    assert result["includes"] == ["doc/"]
    assert result["excludes"] == ["doc/*.html"]
