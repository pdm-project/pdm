"""
This script is used to setup development environment of pdm. It follows the naming
convention of setuptools but it is not basically a setuptools setup script.

After running this script, an editable version of pdm will be installed into
`__packages__`.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
if sys.version_info < (3, 7):
    sys.exit("PDM requires Python 3.7 or higher.")


def main():
    venv_path = BASE_DIR / "env"
    scripts_dir = "Scripts" if os.name == "nt" else "bin"
    venv_python = venv_path / scripts_dir / "python"

    print(f"Creating a venv using {sys.executable} at {venv_path}...", flush=True)
    subprocess.check_call([sys.executable, "-m", "venv", venv_path.as_posix()])

    print("Installing base requirements...", flush=True)
    subprocess.check_call(
        [venv_python.as_posix(), "-m", "pip", "install", "-U", "pip", "pdm"]
    )

    print("Setup project for development...", flush=True)
    venv_pdm = (venv_python.parent / "pdm").as_posix()

    subprocess.check_call([venv_pdm, "use", sys.executable])
    subprocess.check_call([venv_pdm, "config", "parallel_install", "false"])
    subprocess.check_call([venv_pdm, "install", "-vv"])

    pdm_path = (
        BASE_DIR
        / "__pypackages__"
        / ".".join(map(str, sys.version_info[:2]))
        / scripts_dir
        / "pdm"
    ).absolute()

    print(f"\nDeleting venv {venv_path}...", flush=True)
    shutil.rmtree(venv_path, ignore_errors=True)

    print(
        f"An editable version of pdm is installed at {pdm_path}, "
        "you can create an alias for it for convenience.",
        flush=True,
    )


if __name__ == "__main__":
    main()
