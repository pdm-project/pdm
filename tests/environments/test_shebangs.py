import io
import os
import shlex
import zipfile
from pathlib import Path

import pytest

from pdm.environments.local import PythonLocalEnvironment, _get_shebang_path, _is_console_script, _replace_shebang


@pytest.mark.parametrize(
    "executable,is_launcher,expected",
    [
        ("/usr/bin/python", True, b"/usr/bin/python"),
        ("/usr/bin/python", False, b"/usr/bin/python"),
        ("/a path/with space/python", False, shlex.quote("/a path/with space/python").encode("utf-8")),
    ],
)
def test_get_shebang_path(executable, is_launcher, expected):
    assert _get_shebang_path(executable, is_launcher) == expected


def test_is_console_script_unix_and_binary():
    # Non-Windows path: startswith #! => True
    assert _is_console_script(b"#!/usr/bin/env python\nprint('x')\n") is True
    # Undecodable bytes => False
    assert _is_console_script(b"\xff\xfe\xfd") is False


@pytest.mark.skipif(os.name == "nt", reason="Regex branch differs on Windows")
@pytest.mark.parametrize(
    "content,new_exec,expected_prefix",
    [
        (b"#!/usr/bin/python\nprint('hi')\n", b"/new/python", b"#!/new/python\n"),
        (
            b"#!/bin/sh\n'''exec' '/old path/python' \"$0\" \"$@\"\n' '''\nprint('x')\n",
            b"/new/python",
            b"#!/bin/sh\n'''exec' /new/python \"$0\"",
        ),
    ],
)
def test_replace_shebang_unix(tmp_path: Path, content: bytes, new_exec: bytes, expected_prefix: bytes):
    f = tmp_path / "script"
    f.write_bytes(content)
    _replace_shebang(f, new_exec)
    data = f.read_bytes()
    assert data.startswith(expected_prefix)


def test_update_shebangs_changes_scripts_header(project):
    env = PythonLocalEnvironment(project)
    # Create a fake script under the environment's scripts dir
    scripts = Path(env.get_paths()["scripts"])  # ensure exists
    script = scripts / "demo"
    script.write_text("#!/usr/bin/python\nprint('ok')\n", encoding="utf-8")

    new_path = "/opt/python/bin/python"
    # Exercise update_shebangs
    env.update_shebangs(new_path)

    text = script.read_text(encoding="utf-8")
    assert text.splitlines()[0] == f"#!{new_path}"


def test_update_shebangs_ignores_non_target_files_and_dirs(project):
    env = PythonLocalEnvironment(project)
    scripts = Path(env.get_paths()["scripts"])  # ensure exists
    # A non-target extension file
    other = scripts / "notascript.sh"
    other.write_text("#!/usr/bin/python\nprint('no change')\n", encoding="utf-8")
    # A directory
    d = scripts / "adir"
    d.mkdir(exist_ok=True)

    before_other = other.read_text(encoding="utf-8")
    env.update_shebangs("/opt/python/bin/python")
    after_other = other.read_text(encoding="utf-8")
    # Should be unchanged
    assert before_other == after_other


def test_replace_shebang_early_return_when_not_console(tmp_path: Path):
    f = tmp_path / "no_shebang"
    original = b"print('hello')\n"
    f.write_bytes(original)
    _replace_shebang(f, b"/new/python")
    assert f.read_bytes() == original


def _zip_with_main_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w") as zf:
        zf.writestr("__main__.py", "print('ok')\n")
    return buf.getvalue()


def test_is_console_script_windows_zip(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    data = _zip_with_main_bytes()
    assert _is_console_script(data) is True
    # Not a valid zip => False (falls back to text detection which returns False)
    assert _is_console_script(b"not a zip") is False


def test_is_console_script_windows_text_shebang(monkeypatch):
    # On Windows, non-zip scripts with shebang should still be recognized
    monkeypatch.setattr(os, "name", "nt")
    assert _is_console_script(b"#!/usr/bin/env python\r\nprint('x')\r\n") is True


def test_replace_shebang_windows_zip_no_change(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(os, "name", "nt")
    f = tmp_path / "script.exe"
    data = _zip_with_main_bytes()
    f.write_bytes(data)
    _replace_shebang(f, b"C:/Python/python.exe")
    # Should remain unchanged since regex won't match zip content
    assert f.read_bytes() == data
