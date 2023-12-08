def test_help_with_unknown_arguments(pdm):
    result = pdm(["add", "--unknown-args"])
    assert "Usage: pdm add " in result.stderr
    assert result.exit_code == 2
