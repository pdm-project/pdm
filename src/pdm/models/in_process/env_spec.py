from __future__ import annotations

import json
import platform
import site
import sys
import sysconfig


def get_current_env_spec() -> dict[str, str | bool]:
    from dep_logic.tags import Platform

    python_version = f"{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}"
    return {
        "requires_python": f"=={python_version}",
        "platform": str(Platform.current()),
        "implementation": platform.python_implementation().lower(),
        "gil_disabled": sysconfig.get_config_var("Py_GIL_DISABLED") or False,
    }


if __name__ == "__main__":
    for shared_lib in sys.argv[1:]:
        site.addsitedir(shared_lib)
    print(json.dumps(get_current_env_spec(), indent=2))
