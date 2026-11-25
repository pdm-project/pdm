import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pdm.cli import utils
from pdm.cli.actions import check_update


def test_help_with_unknown_arguments(pdm):
    result = pdm(["add", "--unknown-args"])
    assert "usage: pdm add " in result.stderr.lower()
    assert result.exit_code == 2


def test_output_similar_command_when_typo(pdm):
    result = pdm(["instal"])
    assert "install" in result.stderr
    assert result.exit_code == 2


skipif_not_windows = pytest.mark.skipif(os.name != "nt", reason="Windows only")


class UvDetectionTestBase:
    env_name: str

    @pytest.fixture(autouse=True)
    def clean_os_env(self, monkeypatch) -> None:
        monkeypatch.delenv(self.env_name, raising=False)


class TestUvxRunner(UvDetectionTestBase):
    env_name = "UV_CACHE_DIR"

    @pytest.mark.parametrize(
        "path,expected",
        [
            ("archive-v0/F5cKFbuvJzqyyo7y", True),
            ("archive-v1/any-string", True),
            ("archive-v20/no-matter-what", True),
            ("archive-v0", False),  # Missing subdir
            ("archive-v0.1/F5cKFbuvJzqyyo7y", False),
            ("archive-v1rc1/F5cKFbuvJzqyyo7y", False),
            ("archive-v/F5cKFbuvJzqyyo7y", False),
            ("archive-va/F5cKFbuvJzqyyo7y", False),
            ("uv/tools/pdm", False),
            ("pipx/venvs/pdm", False),
            ("", False),
        ],
    )
    def test_is_uvx_runner_with_env_var(self, path: str, expected: bool, tmp_path, monkeypatch):
        cache_dir = str(tmp_path)
        prefix = str(tmp_path / path)
        monkeypatch.setenv(self.env_name, cache_dir)
        monkeypatch.setattr(sys, "prefix", prefix)
        assert utils.is_uvx_runner() is expected

    @pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
    @pytest.mark.parametrize(
        "prefix,expected",
        [
            ("/home/user/.cache/uv/archive-v0/F5cKFbuvJzqyyo7y", True),
            ("/home/user/.cache/uv/archive-v1/F5cKFbuvJzqyyo7y", True),
            ("/home/user/.cache/uv/archive-v2/F5cKFbuvJzqyyo7y", True),
            ("/Users/mac/.cache/uv/archive-v20/F5cKFbuvJzqyyo7y", True),
            ("/home/user/.cache/uv/archive-v0", False),
            ("/home/user/.cache/uv/archive-v0.1", False),
            ("/home/user/.cache/uv/archive-v1.0.0", False),
            ("/Users/mac/.cache/uv/archive-v2.0.0rc1", False),
            ("/home/user/myproject/.venv", False),
            ("/home/user/.cache/uv/archive-va", False),
            ("/Users/mac/.local/pipx/venvs/pdm", False),
            ("/Users/mac/.local/share/uv/tools/pdm", False),
        ],
    )
    def test_is_uvx_runner_without_custom_uv_cache_dir(self, prefix: str, expected: bool, monkeypatch):
        monkeypatch.setattr(sys, "prefix", prefix)
        assert utils.is_uvx_runner() is expected

    @skipif_not_windows
    @pytest.mark.parametrize(
        "prefix,expected",
        [
            (r"C:\Users\alice\AppData\uv\cache\archive-v0\F5cKFbuvJzqyyo7y", True),
            (r"C:\Users\alice\AppData\uv\cache\archive-v1\F5cKFbuvJzqyyo7y", True),
            (r"D:\any-dir\uv\cache\archive-v10\F5cKFbuvJzqyyo7y", True),
            (r"D:\uv\archive-v1.1\F5cKFbuvJzqyyo7y\pdm", False),
            (r"C:\Users\alice\.local\pipx\venvs\pdm", False),
            (r"D:\uv\tools\pdm", False),
            (r"C:\Users\alice\AppData\Roaming\uv\tools\pdm", False),
        ],
    )
    def test_is_uvx_runner_on_windows_without_env(self, prefix: str, expected: bool, monkeypatch):
        monkeypatch.setattr(sys, "prefix", prefix)
        assert utils.is_uvx_runner() is expected


class TestUvTool(UvDetectionTestBase):
    env_name = "UV_TOOL_DIR"

    @skipif_not_windows
    @pytest.mark.parametrize(
        "prefix,tool_dir,expected",
        [
            (r"D:\uv-tools\pdm", "D:/uv-tools", True),
            (r"D:\uv-tools\pdm", "D:/uv-tools/", True),
            (r"D:\uv-tools\pdm", None, False),
            (r"D:\uv-tools\pdm", "C:/uv-tools/", False),
            (r"C:\Users\alice\AppData\uv\cache\archive-v0\F5cKFbuvJzqyyo7y", None, False),
        ],
    )
    def test_windows_uv_tool_installation(self, prefix: str, tool_dir: str | None, expected: bool, monkeypatch):
        if tool_dir:
            monkeypatch.setenv(self.env_name, tool_dir)
        monkeypatch.setattr(sys, "prefix", prefix)
        assert utils.is_uv_tool_installation() is expected

    @skipif_not_windows
    def test_is_uv_tool_installation_windows_oserror(self, monkeypatch):
        """Cover OSError branch on Windows."""
        prefix = r"D:\uv\tools\pdm"
        tool_dir = "D:/uv/tools"
        resolved_path = Path(r"D:\uv\tools")
        monkeypatch.setenv(self.env_name, tool_dir)
        monkeypatch.setattr(sys, "prefix", prefix)
        with (
            patch.object(Path, "samefile", side_effect=OSError),
            patch.object(Path, "resolve", return_value=resolved_path),
        ):
            assert utils.is_uv_tool_installation() is True

    @pytest.mark.parametrize(
        "prefix,tool_dir,expected",
        [
            ("/home/user/.local/share/uv/tools/pdm", None, True),
            (r"C:\Users\alice\AppData\Roaming\uv\tools\pdm", None, True),
            ("/opt/uv/tools/pdm", "/opt/uv/tools", True),
            (r"D:\uv\tools\pdm", r"D:\uv\tools", True),
            ("/opt/uv/tools/pdm", "/opt/other-tools", False),
            (r"D:\uv\tools\pdm", r"D:\other", False),
            ("/usr/local/lib/python3.12", None, False),
            ("/Users/mac/.local/pipx/venvs/pdm", None, False),
        ],
    )
    def test_is_uv_tool_installation(self, prefix: str, tool_dir: str | None, expected: bool, monkeypatch):
        os_sep = "\\" if "\\" in prefix else "/"
        if tool_dir:
            monkeypatch.setenv(self.env_name, tool_dir)
        monkeypatch.setattr(sys, "prefix", prefix)
        monkeypatch.setattr(os, "sep", os_sep)

        assert utils.is_uv_tool_installation() is expected


def test_check_update_uvx_skips(monkeypatch):
    monkeypatch.setattr("pdm.cli.utils.is_uvx_runner", lambda: True)
    get_latest = MagicMock()
    monkeypatch.setattr("pdm.cli.actions.get_latest_version", get_latest)
    project = MagicMock()
    project.core.ui.verbosity = 2
    check_update(project)

    get_latest.assert_not_called()


def test_check_update_uv_tool_installation(monkeypatch):
    monkeypatch.setattr("pdm.cli.utils.is_uvx_runner", lambda: False)
    monkeypatch.setattr("pdm.cli.utils.is_uv_tool_installation", lambda: True)
    monkeypatch.setattr("pdm.cli.actions.get_latest_version", lambda *_: "2.0.0")

    project = MagicMock()
    project.core.version = "1.0.0"
    project.core.ui.verbosity = 100
    project.core.ui.info = MagicMock()

    check_update(project)

    project.core.ui.info.assert_called()
    args, _ = project.core.ui.info.call_args
    assert "uv tool upgrade" in args[0]
