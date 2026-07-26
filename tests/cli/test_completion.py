"""Tests for the completion command"""

import io
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from argcomplete import CompletionFinder
from argcomplete.completers import SuppressCompleter
from argcomplete.shell_integration import shellcode

from pdm.cli.completions import configure_parser
from pdm.core import Core


class TestCompletionFinder(CompletionFinder):
    __test__ = False

    def _init_debug_stream(self):
        pass


def completion_values(*words):
    core = Core()
    configure_parser(core)
    finder = TestCompletionFinder(
        core.parser,
        always_complete_options=False,
        default_completer=SuppressCompleter(),
    )
    line = f"pdm {' '.join(words)}"
    output = io.StringIO()

    class CompletionFinished(Exception):
        pass

    def exit_method(_status):
        raise CompletionFinished

    environment = {
        "COMP_LINE": line,
        "COMP_POINT": str(len(line)),
        "_ARGCOMPLETE": "1",
        "_ARGCOMPLETE_IFS": "\n",
        "_ARGCOMPLETE_SHELL": "bash",
    }
    with patch.dict(os.environ, environment):
        with pytest.raises(CompletionFinished):
            finder(
                core.parser,
                always_complete_options=False,
                exit_method=exit_method,
                output_stream=output,
                default_completer=SuppressCompleter(),
            )
    return {value.rstrip() for value in output.getvalue().splitlines()}


def test_completion_bash(pdm):
    """Test completion for bash shell"""
    result = pdm(["completion", "bash"])
    assert result.exit_code == 0
    assert "BASH completion script for pdm" in result.output


@pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None,
    reason="requires a POSIX bash on PATH",
)
def test_completion_bash_runs_without_bash_completion_pkg(tmp_path):
    """Regression test for #3793.

    The generated bash completion script must work even when the
    ``bash-completion`` package is not loaded (e.g. Git Bash on Windows,
    minimal Linux containers). Before the fix, sourcing the script and
    triggering completion printed::

        bash: __ltrim_colon_completions: command not found

    in the middle of the candidate list.
    """
    bash_script = Path(__file__).resolve().parents[2] / "src" / "pdm" / "cli" / "completions" / "pdm.bash"
    project_root = bash_script.parents[4]
    driver = tmp_path / "drive.sh"
    driver.write_text(
        # Explicitly clear the bash-completion helpers so this test is
        # deterministic even when the host has bash-completion installed.
        "unset -f _get_comp_words_by_ref __ltrim_colon_completions 2>/dev/null\n"
        f"source {bash_script}\n"
        f'PATH="{project_root / ".venv" / "bin"}:$PATH"\n'
        "COMP_WORDS=(pdm '')\n"
        "COMP_CWORD=1\n"
        "COMP_LINE='pdm '\n"
        "COMP_POINT=4\n"
        "COMP_TYPE=9\n"
        # Reasonable default that includes ':' as a wordbreak char,
        # which is what makes __ltrim_colon_completions matter.
        "COMP_WORDBREAKS=$' \\t\\n\"\\'><=;|&(:'\n"
        "COMPREPLY=()\n"
        "_python_argcomplete pdm\n"
        # Surface candidates on stdout, errors on stderr.
        'printf "%s\\n" "${COMPREPLY[@]}"\n'
    )
    proc = subprocess.run(
        ["bash", str(driver)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    # The exact symptoms of the bug:
    assert "command not found" not in proc.stderr, proc.stderr
    assert "_get_comp_words_by_ref" not in proc.stderr, proc.stderr
    assert "__ltrim_colon_completions" not in proc.stderr, proc.stderr
    # Sanity: candidates were produced.
    candidates = set(proc.stdout.split())
    assert {"add", "install", "venv"}.issubset(candidates), proc.stdout


def test_completion_zsh(pdm):
    """Test completion for zsh shell"""
    result = pdm(["completion", "zsh"])
    assert result.exit_code == 0
    assert "#compdef pdm" in result.output


def test_completion_fish(pdm):
    """Test completion for fish shell"""
    result = pdm(["completion", "fish"])
    assert result.exit_code == 0
    assert "FISH completion script for pdm" in result.output


def test_completion_powershell(pdm):
    """Test completion for powershell"""
    result = pdm(["completion", "powershell"])
    assert result.exit_code == 0
    assert "Powershell completion script for pdm" in result.output


def test_completion_pwsh(pdm):
    """Test completion for pwsh (PowerShell Core)"""
    result = pdm(["completion", "pwsh"])
    assert result.exit_code == 0
    assert "Powershell completion script for pdm" in result.output


@pytest.mark.parametrize(
    ("shell", "suffix", "title"),
    [
        ("bash", "bash", "BASH"),
        ("zsh", "zsh", "ZSH"),
        ("fish", "fish", "FISH"),
        ("powershell", "ps1", "Powershell"),
    ],
)
def test_completion_script_is_up_to_date(shell, suffix, title):
    script = Path(__file__).resolve().parents[2] / "src" / "pdm" / "cli" / "completions" / f"pdm.{suffix}"
    assert script.read_text() == f"# {title} completion script for pdm\n" + shellcode(["pdm"], shell=shell)


def test_completion_unsupported_shell(pdm):
    """Test completion with unsupported shell raises error"""
    result = pdm(["completion", "unsupported_shell"])
    assert result.exit_code != 0
    assert "Unsupported shell" in result.stderr


def test_completion_auto_detect(pdm, monkeypatch):
    """Test completion with auto-detected shell"""
    import shellingham

    monkeypatch.setattr(shellingham, "detect_shell", lambda: ("bash", "/bin/bash"))
    result = pdm(["completion"])
    assert result.exit_code == 0
    assert "BASH completion script for pdm" in result.output


def test_completion_auto_detect_unsupported(pdm, monkeypatch):
    """Test completion with auto-detected unsupported shell"""
    import shellingham

    monkeypatch.setattr(shellingham, "detect_shell", lambda: ("csh", "/bin/csh"))
    result = pdm(["completion"])
    assert result.exit_code != 0
    assert "Unsupported shell" in result.stderr


def test_completion_engine_completes_commands_and_options():
    assert {"add", "install", "venv"} <= completion_values("")
    assert {"clear", "info", "list", "remove"} <= completion_values("cache", "")
    assert {"create", "list", "remove"} <= completion_values("venv", "")
    assert {"--group", "--dry-run"} <= completion_values("add", "--")
    assert {"-G", "--group"} <= completion_values("add", "-")


def test_completion_engine_completes_static_values():
    assert completion_values("cache", "clear", "") == {"hashes", "http", "metadata", "packages", "wheels"}
    assert completion_values("export", "--format", "") == {"pylock", "requirements"}
    assert completion_values("export", "--format=r") == {"--format=requirements"}
    assert completion_values("completion", "") == {"bash", "fish", "powershell", "pwsh", "zsh"}


def test_completion_engine_completes_project_values(tmp_path, monkeypatch):
    tmp_path.joinpath("pyproject.toml").write_text(
        """
[project]
dependencies = ["httpx>=0.27"]

[project.optional-dependencies]
docs = ["sphinx"]

[dependency-groups]
test = ["pytest"]

[tool.pdm.scripts]
lint = "ruff check"
"""
    )
    monkeypatch.chdir(tmp_path)

    assert {"default", "docs", "test"} <= completion_values("install", "--group", "")
    assert completion_values("install", "--group", "docs,t") == {"docs,test"}
    assert {"httpx", "pytest", "sphinx"} <= completion_values("remove", "")
    assert completion_values("run", "") == {"lint"}
    assert "lint" in completion_values("")


@pytest.mark.skipif(sys.platform == "win32", reason="argcomplete file completion requires Bash")
def test_completion_engine_uses_file_directives():
    assert completion_values("--config", "")
    assert all(Path(value).is_dir() for value in completion_values("build", "--dest", ""))
