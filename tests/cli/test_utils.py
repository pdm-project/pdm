import os
import platform
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
def test_is_uv_tool_installation(tmp_path, prefix, tool_dir, expected):
    env = {"UV_TOOL_DIR": tool_dir} if tool_dir else {}
    os_sep = "\\" if "\\" in prefix else "/"

    with (
        patch.dict(os.environ, env),
        patch.object(sys, "prefix", prefix),
        patch.object(os, "sep", os_sep),
    ):
        assert utils.is_uv_tool_installation() is expected


@pytest.mark.skipif(
    platform.system() != "Windows",
    reason="Path for Windows only",
)
@pytest.mark.parametrize(
    "prefix,tool_dir,expected",
    [
        (r"D:\uv\tools\pdm", "/D/uv/tools", True),
    ],
)
def test_windows_uv_tool_installation(tmp_path, prefix, tool_dir, expected):
    env = {"UV_TOOL_DIR": tool_dir} if tool_dir else {}
    with (
        patch.dict(os.environ, env),
        patch.object(sys, "prefix", prefix),
    ):
        assert utils.is_uv_tool_installation() is expected


@pytest.mark.skipif(
    platform.system() != "Windows",
    reason="Windows-specific OSError path",
)
def test_is_uv_tool_installation_windows_oserror(monkeypatch):
    """Cover OSError branch on Windows."""
    prefix = r"D:\uv\tools\pdm"
    tool_dir = "/D/uv/tools"
    resolved_path = Path(r"D:\uv\tools")

    with (
        patch.dict(os.environ, {"UV_TOOL_DIR": tool_dir}),
        patch.object(sys, "prefix", prefix),
        patch.object(os, "sep", "\\"),
        patch.object(os, "name", "nt"),
        patch.object(Path, "samefile", side_effect=OSError),
        patch.object(Path, "resolve", return_value=resolved_path),
    ):
        assert utils.is_uv_tool_installation() is True


@pytest.mark.parametrize(
    "path,expected",
    [
        ("uv/archive-v0/F5cKFbuvJzqyyo7y", True),
        ("uv/archive-v1", True),
        ("uv/archive-v0.1", True),
        ("uv/archive-v1.0.0rc1", True),
        ("uv/archive-v/", False),
        ("uv/archive-va/", False),
        ("uv/tools/pdm", False),
        ("other-tool/archive-v0", False),
        ("", False),
    ],
)
def test_is_uvx_runner_with_env_var(tmp_path, path: str, expected: bool):
    cache_dir = str(tmp_path)
    prefix = str(tmp_path / path)
    with (
        patch.dict(os.environ, {"UV_CACHE_DIR": cache_dir}),
        patch.object(sys, "prefix", prefix),
    ):
        assert utils.is_uvx_runner() is expected


@pytest.mark.parametrize(
    "prefix,expected",
    [
        ("/home/user/.cache/uv/archive-v0/F5cKFbuvJzqyyo7y/pdm", True),
        ("/home/user/.cache/uv/archive-v1", True),
        ("/home/user/.cache/uv/archive-v2", True),
        ("/home/user/.cache/uv/archive-v0.1", True),
        ("/home/user/.cache/uv/archive-v1.0.0", True),
        ("/home/user/.cache/uv/archive-v2.0.0rc1", True),
        ("/home/user/.cache/uv/archive-v20", True),
        ("/Users/mac/.local/share/uv/tools/pdm", False),
        ("/home/user/.cache/uv/archive-va", False),
        ("/Users/mac/.local/pipx/venvs/pdm", False),
        ("/home/user/myproject/.venv", False),
    ],
)
def test_is_uvx_runner_without_custom_uv_cache_dir(prefix, expected):
    with (
        patch.dict(os.environ, {}, clear=True),
        patch.object(sys, "prefix", prefix),
    ):
        assert utils.is_uvx_runner() is expected


def test_check_update_uvx_skips(monkeypatch):
    monkeypatch.setattr("pdm.cli.utils.is_uvx_runner", lambda: True)
    project = MagicMock()
    project.core.ui.verbosity = 2
    check_update(project)


def test_check_update_uv_tool_installation(monkeypatch, capsys):
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
