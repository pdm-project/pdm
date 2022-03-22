import json
import os
import sys
import sysconfig


def _running_under_venv() -> bool:
    """This handles PEP 405 compliant virtual environments."""
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def _running_under_regular_virtualenv() -> bool:
    """This handles virtual environments created with pypa's virtualenv."""
    # pypa/virtualenv case
    return hasattr(sys, "real_prefix")


def running_under_virtualenv() -> bool:
    """Return True if we're running inside a virtualenv, False otherwise."""
    return _running_under_venv() or _running_under_regular_virtualenv()


def _get_user_scheme():
    if os.name == "nt":
        return "nt_user"
    if sys.platform == "darwin" and sys._framework:
        return "osx_framework_user"
    return "posix_user"


def get_paths(kind=None, vars=None):
    if kind == "user" and not running_under_virtualenv():
        scheme = _get_user_scheme()
        if scheme not in sysconfig._INSTALL_SCHEMES:
            raise ValueError(
                f"{scheme} is not a valid scheme on the system,"
                "or user site may be disabled."
            )
        return sysconfig.get_paths(scheme, vars=vars)
    else:
        return sysconfig.get_paths(vars=vars)


def main():
    vars = kind = None
    if "_SYSCONFIG_VARS" in os.environ:
        vars = json.loads(os.environ["_SYSCONFIG_VARS"])
    if len(sys.argv) > 1 and sys.argv[1] == "--user":
        kind = "user"
    print(json.dumps(get_paths(kind, vars)))


if __name__ == "__main__":
    main()
