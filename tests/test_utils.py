import os
import pathlib
import sys
import unittest.mock as mock
from pathlib import Path

import pytest
import tomlkit

from pdm import utils
from pdm._types import RepositoryConfig
from pdm.cli import utils as cli_utils
from pdm.cli.filters import GroupSelection
from pdm.exceptions import PdmUsageError, PDMWarning


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


def test_get_trusted_hosts(mocker):
    repository_configs = [
        {
            "url": "https://pypi.org",
            "verify_ssl": False,
        },
        {"url": "https://untrusted.pypi.index", "verify_ssl": True},
        {"url": "https://user:password@trusted1.pypi.index", "verify_ssl": False},
        {"url": "https://user:password@trusted2.pypi.index", "verify_ssl": False},
    ]
    sources = [mocker.create_autospec(RepositoryConfig, instance=False, **config) for config in repository_configs]
    expected = [
        "pypi.org",
        "trusted1.pypi.index",
        "trusted2.pypi.index",
    ]
    received = utils.get_trusted_hosts(sources)
    assert received == expected


@pytest.mark.parametrize(
    "given, expected",
    [
        ("scheme://netloc", "scheme://netloc"),
        ("scheme://netloc/path", "scheme://netloc/path"),
        ("scheme://netloc/path/#", "scheme://netloc/path/"),
        ("scheme://netloc/path#fragment", "scheme://netloc/path"),
        ("scheme://netloc/path;parameters?query#fragment", "scheme://netloc/path;parameters?query"),
    ],
)
def test_url_without_fragments(given, expected):
    received = utils.url_without_fragments(given)
    assert received == expected


@pytest.mark.parametrize(
    "given, expected",
    [
        ((["abc", "def", "ghi"], "/"), ["abc", "/", "def", "/", "ghi"]),
        (([], "/"), []),
        ((["abc"], "/"), ["abc"]),
    ],
)
def test_join_list_with(given, expected):
    items, sep = given
    received = utils.join_list_with(items, sep)
    assert received == expected


class TestGetUserEmailFromGit:
    @mock.patch("pdm.utils.shutil.which", return_value=None)
    def test_no_git(self, no_git_patch):
        with no_git_patch:
            assert utils.get_user_email_from_git() == ("", "")

    @mock.patch(
        "pdm.utils.subprocess.check_output",
        side_effect=[
            utils.subprocess.CalledProcessError(-1, ["git", "config", "user.name"], "No username"),
            utils.subprocess.CalledProcessError(-1, ["git", "config", "user.email"], "No email"),
        ],
    )
    @mock.patch("pdm.utils.shutil.which", return_value="git")
    def test_no_git_username_and_email(self, git_patch, no_git_username_and_email_patch):
        with git_patch:
            with no_git_username_and_email_patch:
                assert utils.get_user_email_from_git() == ("", "")

    @mock.patch(
        "pdm.utils.subprocess.check_output",
        side_effect=[
            "username",
            utils.subprocess.CalledProcessError(-1, ["git", "config", "user.email"], "No email"),
        ],
    )
    @mock.patch("pdm.utils.shutil.which", return_value="git")
    def test_no_git_email(self, git_patch, no_git_email_patch):
        with git_patch:
            with no_git_email_patch:
                assert utils.get_user_email_from_git() == ("username", "")

    @mock.patch(
        "pdm.utils.subprocess.check_output",
        side_effect=[utils.subprocess.CalledProcessError(-1, ["git", "config", "user.name"], "No username"), "email"],
    )
    @mock.patch("pdm.utils.shutil.which", return_value="git")
    def test_no_git_username(self, git_patch, no_git_username_patch):
        with git_patch:
            with no_git_username_patch:
                assert utils.get_user_email_from_git() == ("", "email")

    @mock.patch("pdm.utils.subprocess.check_output", side_effect=["username", "email"])
    @mock.patch("pdm.utils.shutil.which", return_value="git")
    def test_git_username_and_email(self, git_patch, git_username_and_email_patch):
        with git_patch:
            with git_username_and_email_patch:
                assert utils.get_user_email_from_git() == ("username", "email")


@pytest.mark.parametrize(
    "given,expected",
    [
        ("git@github.com/pdm-project/pdm", "ssh://git@github.com/pdm-project/pdm"),
        ("ssh://git@github.com/pdm-project/pdm", "ssh://git@github.com/pdm-project/pdm"),
        ("git+ssh://git@github.com/pdm-project/pdm", "git+ssh://git@github.com/pdm-project/pdm"),
        ("https://git@github.com/pdm-project/pdm", "https://git@github.com/pdm-project/pdm"),
        ("file:///my/local/pdm-project/pdm", "file:///my/local/pdm-project/pdm"),
    ],
)
def test_add_ssh_scheme_to_git_uri(given, expected):
    assert utils.add_ssh_scheme_to_git_uri(given) == expected


class TestUrlToPath:
    def test_non_file_url(self):
        with pytest.raises(AssertionError):
            utils.url_to_path("not_a_file_scheme://netloc/path")

    @pytest.mark.skipif(sys.platform.startswith("win"), reason="Non-Windows test")
    def test_non_windows_non_local_file_url(self):
        with pytest.raises(ValueError):
            utils.url_to_path("file://non_local_netloc/file/url")

    @pytest.mark.skipif(sys.platform.startswith("win"), reason="Non-Windows test")
    def test_non_windows_localhost_local_file_url(self):
        assert utils.url_to_path("file://localhost/local/file/path") == "/local/file/path"

    @pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows test")
    def test_windows_localhost_local_file_url(self):
        assert utils.url_to_path("file://localhost/local/file/path") == "\\local\\file\\path"


# Only testing POSIX-style paths here
@pytest.mark.skipif(sys.platform.startswith("win"), reason="Non-Windows tests")
@pytest.mark.parametrize(
    "given, expected",
    [
        ("/path/to/my/pdm", "file:///path/to/my/pdm"),
        ("/abs/path/to/my/pdm", "file:///abs/path/to/my/pdm"),
        ("/path/to/my/pdm/pyproject.toml", "file:///path/to/my/pdm/pyproject.toml"),
        ("../path/to/my/pdm/pyproject.toml", "file:///abs/path/to/my/pdm/pyproject.toml"),
    ],
)
def test_path_to_url(given, expected):
    if os.path.isabs(given):
        assert utils.path_to_url(given) == expected
    else:
        abs_given = "abs" + str(given).replace("..", "")

        with mock.patch("pdm.utils.os.path.abspath", return_value=abs_given):
            assert utils.path_to_url(given) == expected


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
def test_expand_env_vars_in_auth(given, expected, monkeypatch):
    monkeypatch.setenv("FOO", "hello")
    monkeypatch.setenv("BAR", "wo:rld")
    assert utils.expand_env_vars_in_auth(given) == expected


@pytest.mark.parametrize(
    "os_name,given,expected",
    [
        ("posix", ("match", "repl", "/a/b/match/c/match/d/e"), "/a/b/repl/c/repl/d/e"),
        ("posix", ("old", "new", "/path/to/old/pdm"), "/path/to/new/pdm"),
        ("posix", ("match", "repl", "match/a/math/b/match/c"), "repl/a/math/b/repl/c"),
        ("posix", ("match", "repl", "/some/path"), "/some/path"),
        ("posix", ("match", "repl", ""), ""),
        ("nt", ("old", "new", "C:\\Path\\tO\\old\\pdm"), "C:/Path/tO/new/pdm"),
        ("nt", ("old", "new", "C:\\Path\\tO\\Old\\pdm"), "C:/Path/tO/new/pdm"),
        ("nt", ("old", "new", "C:\\no\\matching\\path"), "C:/no/matching/path"),
    ],
)
def test_path_replace(os_name, given, expected):
    with mock.patch("pdm.utils.os_name", os_name):
        pattern, replace_with, dest = given
        assert utils.path_replace(pattern, replace_with, dest) == expected


# Only testing POSIX-style paths here
@pytest.mark.parametrize(
    "given,expected",
    [
        (("/", "/"), True),
        (("/a", "/"), True),
        (("/a/b", "/a"), True),
        (("/a", "/b"), False),
        (("a", "b"), False),
        (("/a/b", "/c/d"), False),
        (("/a/b/c", "/a"), True),
        (("../a/b/c", "../a"), True),
    ],
)
def test_is_path_relative_to(given, expected):
    path, other = given
    assert utils.is_path_relative_to(path, other) == expected


class TestGetVenvLikePrefix:
    def test_conda_env_with_conda_meta_in_bin(self, tmp_path: Path):
        path = tmp_path / "conda/bin/python3"
        path_parent = path.parent
        path_parent.mkdir(parents=True)
        path.touch()
        path_parent.joinpath("conda-meta").mkdir()
        received = utils.get_venv_like_prefix(path)
        expected = path_parent, True
        assert received == expected

    def test_py_env_with_pyvenv_cfg(self, tmp_path: Path):
        path = tmp_path / "venv/bin/python3"
        bin_path = path.parent
        venv_path = path.parent.parent
        bin_path.mkdir(parents=True)
        path.touch()
        venv_path.joinpath("pyvenv.cfg").touch()

        received = utils.get_venv_like_prefix(str(path))
        expected = venv_path, False
        assert received == expected

    def test_conda_env_with_conda_meta(self, tmp_path: Path):
        path = tmp_path / "conda/bin/python3"
        interpreter_bin_path = path.parent
        interpreter_bin_parent_path = interpreter_bin_path.parent
        interpreter_bin_path.mkdir(parents=True)
        path.touch()
        interpreter_bin_parent_path.joinpath("conda-meta").mkdir()

        received = utils.get_venv_like_prefix(str(path))
        expected = interpreter_bin_parent_path, True
        assert received == expected

    def test_virtual_env(self, monkeypatch):
        path = Path("/my/venv")
        expected = path, False
        monkeypatch.setenv("VIRTUAL_ENV", str(path))
        received = utils.get_venv_like_prefix(path.joinpath("bin", "python3"))
        assert received == expected

    def test_conda_virtual_env(self, monkeypatch):
        path = Path("/my/conda/venv")
        expected = path, True
        monkeypatch.setenv("CONDA_PREFIX", str(path))
        received = utils.get_venv_like_prefix(path.joinpath("bin", "python3"))
        assert received == expected

    def test_no_virtual_env(self):
        path = Path("/not/a/venv/bin/python3")
        expected = None, False
        received = utils.get_venv_like_prefix(str(path))
        assert received == expected


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


@pytest.mark.parametrize(
    "given,expected",
    [
        ("scheme://netloc/path@rev#fragment", "rev"),
        ("scheme://netloc/path@rev", "rev"),
        ("scheme://netloc/path", ""),
        ("scheme://netloc/path#fragment", ""),
    ],
)
def test_get_rev_from_url(given, expected):
    assert utils.get_rev_from_url(given) == expected


@pytest.mark.parametrize(
    "given,expected",
    [
        (("ProjectName", False), "ProjectName"),
        (("ProjectName", True), "projectname"),
        (("1Project_Name", False), "1Project-Name"),
        (("1Project_Name", True), "1project-name"),
        (("Project-Name", False), "Project-Name"),
        (("Project-Name", True), "project-name"),
        (("Project123Name", False), "Project123Name"),
        (("Project123name", True), "project123name"),
        (("123$!ProjectName", False), "123-ProjectName"),
        (("123$!ProjectName", True), "123-projectname"),
        (("123$!Project_Name", False), "123-Project-Name"),
        (("123$!Project_Name", True), "123-project-name"),
        (("$!123Project_Name4", False), "-123Project-Name4"),
        (("$!123Project_Name4", True), "-123project-name4"),
    ],
)
def test_normalize_name(given, expected):
    assert utils.normalize_name(*given) == expected


class TestIsEditable:
    @mock.patch("pdm.utils.is_egg_link", return_value=True)
    @mock.patch("pdm.compat.Distribution")
    def test_is_egg_link(self, distribution, is_egg_link_patch):
        with is_egg_link_patch:
            assert utils.is_editable(distribution) is True

    @mock.patch("pdm.utils.is_egg_link", return_value=False)
    @mock.patch("pdm.compat.Distribution")
    def test_not_direct_url_distribution(self, distribution, is_egg_link_patch):
        distribution.read_text.return_value = None
        with is_egg_link_patch:
            assert utils.is_editable(distribution) is False

    @mock.patch("pdm.utils.is_egg_link", return_value=False)
    @mock.patch("pdm.compat.Distribution")
    def test_direct_url_distribution(self, distribution, is_egg_link_patch):
        distribution.read_text.return_value = """{"dir_info": {"editable": true}}"""
        with is_egg_link_patch:
            assert utils.is_editable(distribution) is True


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


@pytest.mark.parametrize(
    "args,golden",
    [
        ({"groups": [":all"], "excluded_groups": ["web"]}, ["default", "auth", "doc", "test"]),
        ({"groups": [":all"], "excluded_groups": ["web", "auth"]}, ["default", "doc", "test"]),
        ({"groups": [":all"], "excluded_groups": ["default", "test"]}, ["auth", "doc", "web"]),
    ],
)
def test_exclude_optional_groups_from_all(project, args, golden):
    setup_dependencies(project)
    selection = GroupSelection(project, **args)
    assert golden == list(selection)


def test_prod_should_not_be_with_dev(project):
    setup_dependencies(project)
    selection = GroupSelection(project, default=True, dev=False, groups=["test"])
    with pytest.raises(PdmUsageError):
        list(selection)


def test_deprecation_warning():
    with pytest.warns(PDMWarning) as record:
        utils.deprecation_warning("Test warning", raise_since="99.99")
    assert len(record) == 1
    assert str(record[0].message) == "Test warning"

    with pytest.raises(PDMWarning):
        utils.deprecation_warning("Test warning", raise_since="0.0")


def test_comparable_version():
    assert utils.comparable_version("1.2.3") == utils.parse_version("1.2.3")
    assert utils.comparable_version("1.2.3a1+local1") == utils.parse_version("1.2.3a1")


@pytest.mark.parametrize("name", ["foO", "f", "3d", "f3", "333", "foo.bar", "foo-bar", "foo_bar", "foo-_.bar"])
def test_validate_project_name(name):
    assert utils.validate_project_name(name)


@pytest.mark.parametrize("name", ["", "-", ".foo", "foo_", "-3", "foo$bar", "a.3-"])
def test_invalidate_project_name(name):
    assert not utils.validate_project_name(name)


@pytest.mark.parametrize(
    "given,sanitized",
    [("foo", "foo"), ("Foo.Bar", "Foo.Bar"), ("-foo", "foo"), ("Foo%$Bar", "Foo-Bar"), ("Foo$", "Foo")],
)
def test_sanitize_project_name(given, sanitized):
    assert utils.sanitize_project_name(given) == sanitized
