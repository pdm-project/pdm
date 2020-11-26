import os
import site
import sys
import warnings
from distutils.sysconfig import get_python_lib

# Global state to avoid recursive execution
_initialized = False


def get_pypackages_path(maxdepth=5):
    def find_pypackage(path):
        if not os.path.exists(path):
            return None
        packages_name = "__pypackages__/{}/lib".format(
            ".".join(map(str, sys.version_info[:2]))
        )
        for _ in range(maxdepth):
            if os.path.exists(os.path.join(path, packages_name)):
                return os.path.join(path, packages_name)
            if os.path.dirname(path) == path:
                # Root path is reached
                break
            path = os.path.dirname(path)
        return None

    find_paths = [os.getcwd()]

    if getattr(sys, "argv", None):
        script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        find_paths.insert(0, script_dir)

    for path in find_paths:
        result = find_pypackage(path)
        if result:
            return result


def init():
    global _initialized
    if (
        os.getenv("PYTHONPEP582", "").lower() not in ("true", "1", "yes")
        or _initialized
    ):
        # Do nothing if pep 582 is not enabled explicitly
        return
    _initialized = True

    if sys.version_info[0] == 2 and getattr(sys, "argv", None) is None:
        warnings.warn(
            "PEP 582 can't be loaded based on the script path. "
            "As Python 2.7 reached the end of life on 2020/01/01, "
            "please upgrade to Python 3.",
        )
    else:
        script_path = sys.argv[0]
        if os.path.exists(script_path) and os.path.normcase(
            os.path.abspath(script_path)
        ).startswith(os.path.normcase(sys.prefix)):
            return
    libpath = get_pypackages_path()
    if not libpath:
        return
    # First, drop system-sites related paths.
    original_sys_path = sys.path[:]
    known_paths = set()
    system_sites = {
        os.path.normcase(site)
        for site in (
            get_python_lib(plat_specific=False),
            get_python_lib(plat_specific=True),
        )
    }
    for path in system_sites:
        site.addsitedir(path, known_paths=known_paths)
    system_paths = set(
        os.path.normcase(path) for path in sys.path[len(original_sys_path) :]
    )
    original_sys_path = [
        path for path in original_sys_path if os.path.normcase(path) not in system_paths
    ]
    sys.path = original_sys_path

    # Second, add lib directories, ensuring .pth file are processed.
    site.addsitedir(libpath)
