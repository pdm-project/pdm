from __future__ import annotations

import json
import platform
import site
import sys
import sysconfig


def get_current_env_spec(shared_lib: str) -> dict[str, str | bool]:
    site.addsitedir(shared_lib)
    from dep_logic.tags import Platform

    python_version = f"{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}"
    return {
        "requires_python": f"=={python_version}",
        "platform": str(Platform.current()),
        "implementation": platform.python_implementation().lower(),
        "gil_disabled": sysconfig.get_config_var("Py_GIL_DISABLED") or False,
    }


if __name__ == "__main__":
    print(json.dumps(get_current_env_spec(sys.argv[1]), indent=2))
