def test_help_with_unknown_arguments(pdm):
    result = pdm(["add", "--unknown-args"])
    assert "Usage: pdm add " in result.stderr
    assert result.exit_code == 2


def test_output_similar_command_when_typo(pdm):
    result = pdm(["instal"])
    assert "install" in result.stderr
    assert result.exit_code == 2
