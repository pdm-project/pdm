import os
import platform
import sys
from unittest.mock import patch

import pytest

from pdm.cli import utils


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


@pytest.mark.parametrize(
    "path,expected",
    [
        ("uv/archive-v0/F5cKFbuvJzqyyo7y", True),
        ("uv/archive-v1", True),
        ("uv/archive-v0.1", True),
        ("uv/archive-v1.0.0rc1", True),
        ("uv/archive-v/", False),
        ("uv/tools/pdm", False),
        ("other-tool/archive-v0", False),
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
    ],
)
def test_is_uvx_runner_without_custom_uv_cache_dir(prefix, expected):
    with (
        patch.dict(os.environ, {}, clear=True),
        patch.object(sys, "prefix", prefix),
    ):
        assert utils.is_uvx_runner() is expected
