"""Tests for the completion command"""


def test_completion_bash(pdm):
    """Test completion for bash shell"""
    result = pdm(["completion", "bash"])
    assert result.exit_code == 0
    assert "(completion)" in result.output
    assert "bash" in result.output.lower()


def test_completion_zsh(pdm):
    """Test completion for zsh shell"""
    result = pdm(["completion", "zsh"])
    assert result.exit_code == 0
    assert "(completion)" in result.output
    assert "#compdef pdm" in result.output


def test_completion_fish(pdm):
    """Test completion for fish shell"""
    result = pdm(["completion", "fish"])
    assert result.exit_code == 0
    assert "(completion)" in result.output
    assert "complete" in result.output


def test_completion_powershell(pdm):
    """Test completion for powershell"""
    result = pdm(["completion", "powershell"])
    assert result.exit_code == 0
    assert "(completion)" in result.output
    assert "Register-ArgumentCompleter" in result.output


def test_completion_pwsh(pdm):
    """Test completion for pwsh (PowerShell Core)"""
    result = pdm(["completion", "pwsh"])
    assert result.exit_code == 0
    assert "(completion)" in result.output
    assert "Register-ArgumentCompleter" in result.output


def test_completion_unsupported_shell(pdm):
    """Test completion with unsupported shell raises error"""
    result = pdm(["completion", "unsupported_shell"])
    assert result.exit_code != 0
    assert "Unsupported shell" in result.stderr


def test_completion_auto_detect(pdm, monkeypatch):
    """Test completion with auto-detected shell"""
    # Mock shellingham to return bash
    import shellingham

    monkeypatch.setattr(shellingham, "detect_shell", lambda: ("bash", "/bin/bash"))
    result = pdm(["completion"])
    assert result.exit_code == 0
    assert "(completion)" in result.output


def test_completion_auto_detect_unsupported(pdm, monkeypatch):
    """Test completion with auto-detected unsupported shell"""
    import shellingham

    monkeypatch.setattr(shellingham, "detect_shell", lambda: ("csh", "/bin/csh"))
    result = pdm(["completion"])
    assert result.exit_code != 0
    assert "Unsupported shell" in result.stderr
