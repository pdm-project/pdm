import os
import shlex
import subprocess
import sys
import sysconfig
import venv
from pathlib import Path

import pytest


@pytest.mark.parametrize("platform", ["win32", "linux"])
@pytest.mark.parametrize("for_shell", [False, True])
def test_pdm_placeholder_quotes_interpreter_for_target_shell(monkeypatch, tmp_path, platform, for_shell):
    from pdm.cli.commands import run as run_module

    executable = (tmp_path / "python with spaces" / "python.exe").as_posix()
    monkeypatch.setattr(run_module.sys, "executable", executable)
    monkeypatch.setattr(run_module.sys, "platform", platform)

    command, args_interpolated = run_module.interpolate("{pdm} --version", [], for_shell=for_shell)

    assert not args_interpolated
    if platform == "win32" and for_shell:
        assert command == f'"{executable}" -m pdm --version'
    else:
        assert shlex.split(command) == [executable, "-m", "pdm", "--version"]


@pytest.mark.skipif(sys.platform != "win32", reason="Exercises cmd.exe with a real spaced interpreter path")
def test_pdm_shell_placeholder_with_spaced_interpreter(project, tmp_path):
    spaced_venv = tmp_path / "python with spaces"
    venv.EnvBuilder(with_pip=False).create(spaced_venv)
    site_packages = spaced_venv / "Lib" / "site-packages"
    # Reuse the checkout and its installed test dependencies without installing into the temporary venv.
    paths = [str(Path(__file__).resolve().parents[2] / "src"), sysconfig.get_path("purelib")]
    (site_packages / "pdm_test.pth").write_text("\n".join(paths) + "\n", encoding="utf-8")
    project.pyproject.settings["scripts"] = {"test_script": {"shell": "{pdm} -V > output.txt"}}
    project.pyproject.write()
    environment = os.environ.copy()
    for key in ("VIRTUAL_ENV", "CONDA_PREFIX", "PYTHONHOME", "PYTHONPATH", "NO_SITE_PACKAGES", "PDM_PYTHON"):
        environment.pop(key, None)
    environment.update(
        PDM_CONFIG_FILE=str(project.global_config.config_file), PDM_CHECK_UPDATE="0", PYTHONIOENCODING="utf-8"
    )

    result = subprocess.run(
        [
            str(spaced_venv / "Scripts" / "python.exe"),
            "-m",
            "pdm",
            "run",
            "test_script",
        ],
        cwd=project.root,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert (project.root / "output.txt").read_text().strip().startswith("PDM, version")
