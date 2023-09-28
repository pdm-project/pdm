import pathlib
import sys
import unittest.mock as mock

import pytest
import tomlkit
from packaging.version import Version

from pdm import utils
from pdm._types import RepositoryConfig
from pdm.cli import utils as cli_utils
from pdm.cli.filters import GroupSelection
from pdm.exceptions import PdmUsageError


@pytest.mark.parametrize(
    "given, dirname",
    [
        ((None, None, None), "test_dirname1"),
        (("test_suffix", None, None), "test_dirname2"),
        (("test_suffix", "test_prefix", None), "test_dirname3"),
        (("test_suffix", "test_prefix", "test_dir"), "test_dirname4"),
        ((None, "test_prefix", None), "test_dirname5"),
        ((None, "test_prefix", "test_dir"), "test_dirname6"),
        ((None, None, "test_dir"), "test_dirname7"),
        ((None, "test_prefix", "test_dir"), "test_dirname8"),
        (("test_prefix", None, "test_dir"), "test_dirname9"),
    ],
)
@mock.patch("pdm.utils.atexit.register")
@mock.patch("pdm.utils.os.makedirs")
@mock.patch("pdm.utils.tempfile.mkdtemp")
def test_create_tracked_tempdir(mock_tempfile_mkdtemp, mock_os_makedirs, mock_atexit_register, given, dirname):
    test_suffix, test_prefix, test_dir = given
    mock_tempfile_mkdtemp.return_value = dirname
    received_dirname = utils.create_tracked_tempdir(suffix=test_suffix, prefix=test_prefix, dir=dirname)
    mock_tempfile_mkdtemp.assert_called_once_with(suffix=test_suffix, prefix=test_prefix, dir=dirname)
    mock_os_makedirs.assert_called_once_with(dirname, mode=0o777, exist_ok=True)
    mock_atexit_register.assert_called()
    assert received_dirname == dirname


def test_get_trusted_hosts():
    test_source1 = mock.create_autospec(RepositoryConfig, instance=False, url="https://pypi.org", verify_ssl=False)
    test_source2 = mock.create_autospec(
        RepositoryConfig, instance=False, url="https://untrusted.pypi.org", verify_ssl=True
    )
    test_source3 = mock.create_autospec(
        RepositoryConfig, instance=False, url="https://user:password@trusted.pypi.org", verify_ssl=False
    )
    test_source4 = mock.create_autospec(
        RepositoryConfig, instance=False, url="https://user:password@another.trusted.pypi.org", verify_ssl=False
    )
    test_sources = [
        test_source1,
        test_source2,
        test_source3,
        test_source4,
    ]
    expected = [
        "pypi.org",
        "trusted.pypi.org",
        "another.trusted.pypi.org",
    ]
    received = utils.get_trusted_hosts(test_sources)
    assert received == expected


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
    target = tomlkit.item(
        {
            "existing_dict": {"foo": "bar", "hello": "world"},
            "existing_list": ["hello"],
        }
    )
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
        ({"default": True, "dev": None, "groups": ()}, ["default", "test", "doc"]),
        (
            {"default": True, "dev": None, "groups": [":all"]},
            ["default", "web", "auth", "test", "doc"],
        ),
        (
            {"default": True, "dev": True, "groups": ["web"]},
            ["default", "web", "test", "doc"],
        ),
        (
            {"default": True, "dev": None, "groups": ["web"]},
            ["default", "web", "test", "doc"],
        ),
        ({"default": True, "dev": None, "groups": ["test"]}, ["default", "test"]),
        (
            {"default": True, "dev": None, "groups": ["test", "web"]},
            ["default", "test", "web"],
        ),
        ({"default": True, "dev": False, "groups": ["web"]}, ["default", "web"]),
        ({"default": False, "dev": None, "groups": ()}, ["test", "doc"]),
    ],
)
def test_dependency_group_selection(project, args, golden):
    setup_dependencies(project)
    selection = GroupSelection(project, **args)
    assert sorted(golden) == sorted(selection)


def test_prod_should_not_be_with_dev(project):
    setup_dependencies(project)
    selection = GroupSelection(project, default=True, dev=False, groups=["test"])
    with pytest.raises(PdmUsageError):
        list(selection)


def test_deprecation_warning():
    with pytest.warns(FutureWarning) as record:
        utils.deprecation_warning("Test warning", raise_since="99.99")
    assert len(record) == 1
    assert str(record[0].message) == "Test warning"

    with pytest.raises(FutureWarning):
        utils.deprecation_warning("Test warning", raise_since="0.0")


def test_comparable_version():
    assert utils.comparable_version("1.2.3") == Version("1.2.3")
    assert utils.comparable_version("1.2.3a1+local1") == Version("1.2.3a1")
