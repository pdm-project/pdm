"""AI-assisted preservation controls for the PEP 582 shell setup recipe."""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest
from pytest_mock import MockerFixture

from pdm.cli.actions import print_pep582_command
from pdm.project import Project

pytestmark = pytest.mark.skipif(os.name == "nt", reason="Matches the admitted POSIX-only regression scope")


@pytest.mark.parametrize("shell", ["BaSh", "sh", "dash", "AUTO"])
@pytest.mark.parametrize(
    "lib_path",
    ["/opt/pdm/pep582", '/opt/space dir/雪/$HOME/$(printf injected)/`printf injected`/a"b\\c;*/pep582'],
)
@pytest.mark.parametrize("pythonpath", [None, "", ":./relative path:/old/O'Brien/$HOME/*::/last path:"])
def test_pep582_setup_preserves_literals_order_and_repeated_exports(
    project: Project, mocker: MockerFixture, shell: str, lib_path: str, pythonpath: str | None
) -> None:
    executable = shutil.which("bash" if shell == "AUTO" else shell.lower())
    assert executable is not None, f"Required shell is unavailable: {shell}"
    mocker.patch("pdm.cli.actions.get_pep582_path", return_value=lib_path)
    detect_shell = mocker.patch("shellingham.detect_shell", return_value=("bash", executable))
    echo = mocker.patch.object(project.core.ui, "echo")

    assert print_pep582_command(project, shell) is None

    echo.assert_called_once()
    if shell == "AUTO":
        detect_shell.assert_called_once_with()
    else:
        detect_shell.assert_not_called()
    script = echo.call_args.args[0]
    # A child shell observes only exported variables. NUL separates exact values,
    # including empty search entries, without stripping spaces from the output.
    observe = '\n/bin/sh -c \'printf "%s\\000" "$PYTHONPATH"\'\n'
    env = {"PATH": "/usr/bin:/bin"}
    if pythonpath is not None:
        env["PYTHONPATH"] = pythonpath
    result = subprocess.run(
        [executable, "-c", script + observe + script + observe],
        env=env,
        capture_output=True,
        timeout=5,
    )

    assert result.returncode == 0, repr(result.stderr)
    first = f"{lib_path}:{pythonpath}" if pythonpath else lib_path
    second = f"{lib_path}:{first}"
    assert result.stdout == f"{first}\0{second}\0".encode(), repr(result.stdout)
