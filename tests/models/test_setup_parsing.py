import pytest

from pdm.models.setup import Setup


@pytest.mark.parametrize(
    "content, result",
    [
        (
            """[metadata]
name = foo
version = 0.1.0
""",
            Setup("foo", "0.1.0"),
        ),
        (
            """[metadata]
name = foo
version = attr:foo.__version__
""",
            Setup("foo", "0.0.0"),
        ),
        (
            """[metadata]
name = foo
version = 0.1.0

[options]
python_requires = >=3.6
install_requires =
    click
    requests
[options.extras_require]
tui =
    rich
""",
            Setup("foo", "0.1.0", ["click", "requests"], {"tui": ["rich"]}, ">=3.6"),
        ),
    ],
)
def test_parse_setup_cfg(content, result, tmp_path):
    tmp_path.joinpath("setup.cfg").write_text(content)
    assert Setup.from_directory(tmp_path) == result


@pytest.mark.parametrize(
    "content,result",
    [
        (
            """from setuptools import setup

setup(name="foo", version="0.1.0")
""",
            Setup("foo", "0.1.0"),
        ),
        (
            """import setuptools

setuptools.setup(name="foo", version="0.1.0")
""",
            Setup("foo", "0.1.0"),
        ),
        (
            """from setuptools import setup

kwargs = {"name": "foo", "version": "0.1.0"}
setup(**kwargs)
""",
            Setup("foo", "0.1.0"),
        ),
        (
            """from setuptools import setup
name = 'foo'
setup(name=name, version="0.1.0")
""",
            Setup("foo", "0.1.0"),
        ),
        (
            """from setuptools import setup

setup(name="foo", version="0.1.0", install_requires=['click', 'requests'],
      python_requires='>=3.6', extras_require={'tui': ['rich']})
""",
            Setup("foo", "0.1.0", ["click", "requests"], {"tui": ["rich"]}, ">=3.6"),
        ),
        (
            """from setuptools import setup

version = open('__version__.py').read().strip()

setup(name="foo", version=version)
""",
            Setup("foo", "0.0.0"),
        ),
    ],
)
def test_parse_setup_py(content, result, tmp_path):
    tmp_path.joinpath("setup.py").write_text(content)
    assert Setup.from_directory(tmp_path) == result


def test_parse_pyproject_toml(tmp_path):
    content = """[project]
name = "foo"
version = "0.1.0"
requires-python = ">=3.6"
dependencies = ["click", "requests"]

[project.optional-dependencies]
tui = ["rich"]
"""
    tmp_path.joinpath("pyproject.toml").write_text(content)
    result = Setup("foo", "0.1.0", ["click", "requests"], {"tui": ["rich"]}, ">=3.6")
    assert Setup.from_directory(tmp_path) == result
