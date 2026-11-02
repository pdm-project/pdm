from __future__ import annotations

import os
import shutil
import subprocess

import pytest
from pytest_mock import MockerFixture

from pdm.cli.actions import print_pep582_command
from pdm.project import Project


@pytest.mark.skipif(os.name == "nt", reason="Bash setup is for POSIX environments")
@pytest.mark.parametrize("lib_path", ["/opt/pdm/pep582", "/opt/O'Brien/pdm/pep582"])
@pytest.mark.parametrize("pythonpath", ["", "/existing/packages"])
def test_pep582_bash_setup_preserves_installation_path(
    project: Project, mocker: MockerFixture, lib_path: str, pythonpath: str
) -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("Bash is required to evaluate the setup command")
    mocker.patch("pdm.cli.actions.get_pep582_path", return_value=lib_path)
    echo = mocker.patch.object(project.core.ui, "echo")

    print_pep582_command(project, "bash")

    echo.assert_called_once()
    script = echo.call_args.args[0]
    result = subprocess.run(
        [bash, "--noprofile", "--norc", "-c", script + '\nprintf "%s" "$PYTHONPATH"'],
        env={"PYTHONPATH": pythonpath},
        capture_output=True,
        timeout=5,
    )
    assert result.returncode == 0, repr(result.stderr)
    expected = f"{lib_path}:{pythonpath}" if pythonpath else lib_path
    assert result.stdout == expected.encode(), repr(result.stdout)
