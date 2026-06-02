"""Tests for the completion command"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest


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
    driver = tmp_path / "drive.sh"
    driver.write_text(
        # Explicitly clear the bash-completion helpers so this test is
        # deterministic even when the host has bash-completion installed.
        "unset -f _get_comp_words_by_ref __ltrim_colon_completions 2>/dev/null\n"
        f"source {bash_script}\n"
        "COMP_WORDS=(pdm '')\n"
        "COMP_CWORD=1\n"
        # Reasonable default that includes ':' as a wordbreak char,
        # which is what makes __ltrim_colon_completions matter.
        "COMP_WORDBREAKS=$' \\t\\n\"\\'><=;|&(:'\n"
        "COMPREPLY=()\n"
        "_pdm_a919b69078acdf0a_complete\n"
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
