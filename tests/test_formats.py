from pdm.formats import pipfile, poetry, requirements
from tests import FIXTURES


def test_convert_pipfile():
    golden_file = FIXTURES / "Pipfile"
    assert pipfile.check_fingerprint(golden_file)
    result = pipfile.convert(golden_file)

    assert result["allow_prereleases"]
    assert result["python_requires"] == ">=3.6"

    assert not result["dev-dependencies"]

    assert result["dependencies"]["requests"] == "*"
    assert result["dependencies"]["pywinusb"]["version"] == "*"
    assert result["dependencies"]["pywinusb"]["marker"] == 'sys_platform == "win32"'

    assert result["source"][0]["url"] == "https://pypi.python.org/simple"


def test_convert_requirements_file():
    golden_file = FIXTURES / "requirements.txt"
    assert requirements.check_fingerprint(golden_file)
    result = requirements.convert(golden_file)

    assert len(result["source"]) == 2
    assert result["dependencies"]["webassets"] == "==2.0"
    assert result["dependencies"]["whoosh"]["marker"] == 'sys_platform == "win32"'
    assert result["dependencies"]["pip"]["editable"]
    assert result["dependencies"]["pip"]["git"] == "https://github.com/pypa/pip.git"


def test_convert_poetry():
    golden_file = FIXTURES / "pyproject-poetry.toml"
    assert poetry.check_fingerprint(golden_file)
    result = poetry.convert(golden_file)

    assert result["author"] == "Sébastien Eustace <sebastien@eustace.io>"
    assert result["name"] == "poetry"
    assert result["version"] == "1.0.0"
    assert "Repository" in result["project_urls"]
    assert result["python_requires"] == ">=2.7,<4.0,!=3.0.*,!=3.1.*,!=3.2.*,!=3.3.*"
    assert result["dependencies"]["cleo"]["marker"] == 'python_version ~= "2.7"'
    assert result["dependencies"]["cachecontrol"]["marker"] == (
        'python_version >= "3.4" and python_version < "4.0"'
    )
    assert "psycopg2" not in result["dependencies"]
    assert "psycopg2" in result["pgsql-dependencies"]
    assert sorted(result["extras"]) == ["mysql", "pgsql"]
    assert len(result["dev-dependencies"]) == 2

    assert result["cli"] == {"poetry": "poetry.console:run"}
    assert result["entry_points"]["blogtool.parsers"] == {
        ".rst": "some_module:SomeClass"
    }
