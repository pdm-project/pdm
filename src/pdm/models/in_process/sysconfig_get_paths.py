import json
import os
import sys
import sysconfig


def _running_under_venv():
    """This handles PEP 405 compliant virtual environments."""
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def _running_under_regular_virtualenv():
    """This handles virtual environments created with pypa's virtualenv."""
    # pypa/virtualenv case
    return hasattr(sys, "real_prefix")


def running_under_virtualenv():
    """Return True if we're running inside a virtualenv, False otherwise."""
    return _running_under_venv() or _running_under_regular_virtualenv()


def _get_user_scheme():
    if os.name == "nt":
        return "nt_user"
    if sys.platform == "darwin" and sys._framework:
        return "osx_framework_user"
    return "posix_user"


def get_paths(kind="default", vars=None):
    scheme_names = sysconfig.get_scheme_names()
    if kind == "user" and not running_under_virtualenv():
        scheme = _get_user_scheme()
        if scheme not in scheme_names:
            raise ValueError("{} is not a valid scheme on the system, or user site may be disabled.".format(scheme))
        return sysconfig.get_paths(scheme, vars=vars)
    else:
        if sys.platform == "darwin" and "osx_framework_library" in scheme_names and kind == "prefix":
            return sysconfig.get_paths("posix_prefix", vars=vars)
        return sysconfig.get_paths(vars=vars)


def main():
    vars = None
    if "_SYSCONFIG_VARS" in os.environ:
        vars = json.loads(os.environ["_SYSCONFIG_VARS"])
    kind = sys.argv[1] if len(sys.argv) > 1 else "default"
    print(json.dumps(get_paths(kind, vars)))


if __name__ == "__main__":
    main()
