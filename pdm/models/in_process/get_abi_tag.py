# mypy: ignore-errors
import json
import platform
import sys
import warnings
from sysconfig import get_config_var

INTERPRETER_SHORT_NAMES = {
    "python": "py",  # Generic.
    "cpython": "cp",
    "pypy": "pp",
    "ironpython": "ip",
    "jython": "jy",
}


def get_abbr_impl():
    """Returns the name of the running interpreter."""
    try:
        name = sys.implementation.name  # type: ignore
    except AttributeError:  # pragma: no cover
        # Python 2.7 compatibility.
        name = platform.python_implementation().lower()

    return INTERPRETER_SHORT_NAMES.get(name) or name


def get_flag(var, fallback, expected=True, warn=True):
    """Use a fallback value for determining SOABI flags if the needed config
    var is unset or unavailable."""
    val = get_config_var(var)
    if val is None:
        if warn:
            warnings.warn(
                "Config variable '{0}' is unset, Python ABI tag may "
                "be incorrect".format(var),
                RuntimeWarning,
                2,
            )
        return fallback
    return val == expected


if __name__ == "__main__":
    soabi = get_config_var("SOABI")
    impl = get_abbr_impl()
    python_version = sys.version_info[:2]
    abi = None

    if not soabi and impl in {"cp", "pp"} and hasattr(sys, "maxunicode"):
        d = ""
        m = ""
        u = ""
        is_cpython = impl == "cp"
        if get_flag("Py_DEBUG", hasattr(sys, "gettotalrefcount"), warn=False):
            d = "d"
        if python_version < (3, 8) and get_flag(
            "WITH_PYMALLOC", is_cpython, warn=False
        ):
            m = "m"
        if python_version < (3, 3) and get_flag(
            "Py_UNICODE_SIZE",
            sys.maxunicode == 0x10FFFF,
            expected=4,
            warn=False,
        ):
            u = "u"
        abi = "%s%s%s%s%s" % (impl, "".join(map(str, python_version)), d, m, u)
    elif soabi and soabi.startswith("cpython-"):
        abi = "cp" + soabi.split("-")[1]
    elif soabi:
        abi = soabi.replace(".", "_").replace("-", "_")

    print(json.dumps(abi))
