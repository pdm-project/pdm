import pathlib
import sys

import pytest

from pdm import utils
from pdm.cli import utils as cli_utils
from pdm.exceptions import PdmUsageError


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


def compare_python_paths(path1, path2):
    return path1.parent == path2.parent


@pytest.mark.path
def test_find_python_in_path(tmp_path):
    assert utils.find_python_in_path(sys.executable) == pathlib.Path(sys.executable).absolute()

    posix_path_to_executable = pathlib.Path(sys.executable)
    assert compare_python_paths(
        utils.find_python_in_path(sys.prefix),
        posix_path_to_executable,
    )

    assert not utils.find_python_in_path(tmp_path)


def test_merge_dictionary():
    target = {
        "existing_dict": {"foo": "bar", "hello": "world"},
        "existing_list": ["hello"],
    }
    input_dict = {
        "existing_dict": {"foo": "baz"},
        "existing_list": ["world"],
        "new_dict": {"name": "Sam"},
    }
    cli_utils.merge_dictionary(target, input_dict)
    assert target == {
        "existing_dict": {"foo": "baz", "hello": "world"},
        "existing_list": ["hello", "world"],
        "new_dict": {"name": "Sam"},
    }


def setup_dependencies(project):
    project.pyproject.metadata.update(
        {
            "dependencies": ["requests"],
            "optional-dependencies": {"web": ["flask"], "auth": ["passlib"]},
        }
    )
    project.pyproject.settings.update({"dev-dependencies": {"test": ["pytest"], "doc": ["mkdocs"]}})
    project.pyproject.write()


@pytest.mark.parametrize(
    "args,golden",
    [
        ((True, None, ()), ["default", "test", "doc"]),
        ((True, None, [":all"]), ["default", "web", "auth", "test", "doc"]),
        ((True, True, ["web"]), ["default", "web", "test", "doc"]),
        ((True, None, ["web"]), ["default", "web", "test", "doc"]),
        ((True, None, ["test"]), ["default", "test"]),
        ((True, None, ["test", "web"]), ["default", "test", "web"]),
        ((True, False, ["web"]), ["default", "web"]),
        ((False, None, ()), ["test", "doc"]),
    ],
)
def test_dependency_group_selection(project, args, golden):
    setup_dependencies(project)
    target = cli_utils.translate_groups(project, *args)
    assert sorted(golden) == sorted(target)


def test_prod_should_not_be_with_dev(project):
    setup_dependencies(project)
    with pytest.raises(PdmUsageError):
        cli_utils.translate_groups(project, True, False, ("test",))


def test_deprecation_warning():
    with pytest.warns(DeprecationWarning) as record:
        utils.deprecation_warning("Test warning", raise_since="99.99")
    assert len(record) == 1
    assert str(record[0].message) == "Test warning"

    with pytest.raises(DeprecationWarning):
        utils.deprecation_warning("Test warning", raise_since="0.0")
