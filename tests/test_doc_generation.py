import argparse

from tasks.render_reference_docs import render_parser


def test_cli_reference_includes_command_notes():
    parser = argparse.ArgumentParser(description="Command summary", epilog="Keep pyproject.toml and pdm.lock.")
    parser.add_argument("--check", action="store_true", help="Check the saved state")

    rendered = render_parser(parser, "example")

    assert "> Command summary" in rendered
    assert "Keep `pyproject.toml` and `pdm.lock`." in rendered
    assert rendered.index("--check") < rendered.index("Keep `pyproject.toml`")
