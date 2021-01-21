import pathlib
import sys

import pytest

from pdm import utils
from pdm.cli import utils as cli_utils
from pdm.exceptions import PdmException


@pytest.mark.parametrize(
    "given,expected",
    [
        ("test", "test"),
        ("", ""),
        ("${FOO}", "hello"),
        ("$FOO", "$FOO"),
        ("${BAR}", "${BAR}"),
        ("%FOO%", "%FOO%"),
        ("${FOO}_${FOO}", "hello_hello"),
    ],
)
def test_expand_env_vars(given, expected, monkeypatch):
    monkeypatch.setenv("FOO", "hello")
    assert utils.expand_env_vars(given) == expected


@pytest.mark.parametrize(
    "given,expected",
    [
        ("https://example.org/path?arg=1", "https://example.org/path?arg=1"),
        (
            "https://${FOO}@example.org/path?arg=1",
            "https://hello@example.org/path?arg=1",
        ),
        (
            "https://${FOO}:${BAR}@example.org/path?arg=1",
            "https://hello:wo%3Arld@example.org/path?arg=1",
        ),
        (
            "https://${FOOBAR}@example.org/path?arg=1",
            "https://%24%7BFOOBAR%7D@example.org/path?arg=1",
        ),
    ],
)
def test_expend_env_vars_in_auth(given, expected, monkeypatch):
    monkeypatch.setenv("FOO", "hello")
    monkeypatch.setenv("BAR", "wo:rld")
    assert utils.expand_env_vars_in_auth(given) == expected


def test_find_python_in_path(tmp_path):

    assert (
        cli_utils.find_python_in_path(sys.executable)
        == pathlib.Path(sys.executable).as_posix()
    )
    assert (
        cli_utils.find_python_in_path(sys.prefix)
        .lower()
        .startswith(pathlib.Path(sys.executable).as_posix().lower())
    )
    with pytest.raises(PdmException):
        cli_utils.find_python_in_path(tmp_path)
