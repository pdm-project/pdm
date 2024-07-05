"""
A collection of functions that need to be called via a subprocess call.
"""

from __future__ import annotations

import contextlib
import functools
import json
import os
import subprocess
import tempfile
from typing import Any, Generator

from pdm.compat import resources_path
from pdm.models.markers import EnvSpec


@contextlib.contextmanager
def _in_process_script(name: str) -> Generator[str, None, None]:
    with resources_path(__name__, name) as script:
        yield str(script)


def get_sys_config_paths(executable: str, vars: dict[str, str] | None = None, kind: str = "default") -> dict[str, str]:
    """Return the sys_config.get_paths() result for the python interpreter"""
    env = os.environ.copy()
    env.pop("__PYVENV_LAUNCHER__", None)
    if vars is not None:
        env["_SYSCONFIG_VARS"] = json.dumps(vars)

    with _in_process_script("sysconfig_get_paths.py") as script:
        cmd = [executable, "-Es", script, kind]
        return json.loads(subprocess.check_output(cmd, env=env))


def parse_setup_py(executable: str, path: str) -> dict[str, Any]:
    """Parse setup.py and return the kwargs"""
    with _in_process_script("parse_setup.py") as script:
        _, outfile = tempfile.mkstemp(suffix=".json")
        cmd = [executable, "-Es", script, path, outfile]
        subprocess.check_call(cmd)
        with open(outfile, "rb") as fp:
            return json.load(fp)


@functools.lru_cache
def get_env_spec(executable: str) -> EnvSpec:
    """Get the environment spec of the python interpreter"""
    with _in_process_script("env_spec.py") as script:
        return EnvSpec.from_spec(**json.loads(subprocess.check_output([executable, "-Es", script])))
