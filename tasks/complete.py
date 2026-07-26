from pathlib import Path

from argcomplete.shell_integration import shellcode

COMPLETIONS = Path(__file__).parent.parent / "src/pdm/cli/completions"


def main():
    for shell, suffix, title in (
        ("bash", "bash", "BASH"),
        ("zsh", "zsh", "ZSH"),
        ("fish", "fish", "FISH"),
        ("powershell", "ps1", "Powershell"),
    ):
        header = f"# {title} completion script for pdm\n"
        COMPLETIONS.joinpath(f"pdm.{suffix}").write_text(header + shellcode(["pdm"], shell=shell))


if __name__ == "__main__":
    main()
