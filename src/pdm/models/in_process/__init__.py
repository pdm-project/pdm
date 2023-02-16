"""
A collection of functions that need to be called via a subprocess call.
"""
from __future__ import annotations

import contextlib
import functools
import json
import os
import subprocess
from typing import Any, Generator

from pdm.compat import resources_path


@contextlib.contextmanager
def _in_process_script(name: str) -> Generator[str, None, None]:
    with resources_path(__name__, name) as script:
        yield str(script)


@functools.lru_cache()
def get_python_abi_tag(executable: str) -> str:
    with _in_process_script("get_abi_tag.py") as script:
        return json.loads(subprocess.check_output(args=[executable, "-Es", script]))


def get_sys_config_paths(executable: str, vars: dict[str, str] | None = None, kind: str = "default") -> dict[str, str]:
    """Return the sys_config.get_paths() result for the python interpreter"""
    env = os.environ.copy()
    env.pop("__PYVENV_LAUNCHER__", None)
    if vars is not None:
        env["_SYSCONFIG_VARS"] = json.dumps(vars)

    with _in_process_script("sysconfig_get_paths.py") as script:
        cmd = [executable, "-Es", script, kind]
        return json.loads(subprocess.check_output(cmd, env=env))


def get_pep508_environment(executable: str) -> dict[str, str]:
    """Get PEP 508 environment markers dict."""
    with _in_process_script("pep508.py") as script:
        args = [executable, "-Es", script]
        return json.loads(subprocess.check_output(args))


def parse_setup_py(executable: str, path: str) -> dict[str, Any]:
    """Parse setup.py and return the kwargs"""
    with _in_process_script("parse_setup.py") as script:
        cmd = [executable, "-Es", script, path]
        return json.loads(subprocess.check_output(cmd))
