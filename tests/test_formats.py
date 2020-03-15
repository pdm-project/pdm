from pdm.formats import pipfile, requirements
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
