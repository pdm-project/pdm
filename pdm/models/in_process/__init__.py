"""
A collection of functions that need to be called via a subprocess call.
"""
import functools
import json
import os
import subprocess
from pathlib import Path
from typing import Dict, Optional

FOLDER_PATH = Path(__file__).parent


@functools.lru_cache()
def get_python_abi_tag(executable: str) -> str:
    script = str(FOLDER_PATH / "get_abi_tag.py")
    return json.loads(subprocess.check_output(args=[executable, "-Es", script]))


def get_sys_config_paths(
    executable: str, vars: Optional[Dict[str, str]] = None
) -> Dict[str, str]:
    """Return the sys_config.get_paths() result for the python interpreter"""
    env = os.environ.copy()
    env.pop("__PYVENV_LAUNCHER__", None)
    if not vars:
        args = [
            executable,
            "-Esc",
            "import sysconfig,json;print(json.dumps(sysconfig.get_paths()))",
        ]
        return json.loads(subprocess.check_output(args))
    else:
        os_name = os.name
        scheme = "posix_prefix" if os_name == "posix" else os.name
        env.update(SYSCONFIG_VARS=json.dumps(vars))
        args = [
            executable,
            "-Esc",
            "import os,sysconfig,json;print(json.dumps(sysconfig."
            f"get_paths({scheme!r}, vars=json.loads(os.getenv('SYSCONFIG_VARS')))))",
        ]
        return json.loads(subprocess.check_output(args, env=env))


def get_pep508_environment(executable: str) -> Dict[str, str]:
    """Get PEP 508 environment markers dict."""
    script = str(FOLDER_PATH / "pep508.py")
    args = [executable, "-Es", script]
    return json.loads(subprocess.check_output(args))
