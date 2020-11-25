import os
import site
import sys
from distutils.sysconfig import get_python_lib

# Global state to avoid recursive execution
_initialized = False


def get_pypackages_path(maxdepth=5):
    def find_pypackage(path):
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

    script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    return find_pypackage(script_dir) or find_pypackage(os.getcwd())


def init():
    global _initialized
    if (
        os.getenv("PYTHONPEP582", "").lower() not in ("true", "1", "yes")
        or _initialized
    ):
        # Do nothing if pep 582 is not enabled explicitly
        return
    _initialized = True
    # First, drop system-sites related paths.
    libpath = get_pypackages_path()
    if not libpath:
        return
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
