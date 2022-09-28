from pathlib import Path

import pycomplete

from pdm.core import Core

COMPLETIONS = Path(__file__).parent.parent / "src/pdm/cli/completions"


def main():
    core = Core()
    core.init_parser()

    completer = pycomplete.Completer(core.parser, ["pdm"])
    for shell in ("bash", "fish"):
        COMPLETIONS.joinpath(f"pdm.{shell}").write_text(completer.render(shell))


if __name__ == "__main__":
    main()
