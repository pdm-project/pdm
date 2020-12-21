import os
import site
import sys
import warnings


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


def main():

    self_path = os.path.normcase(os.path.dirname(os.path.abspath(__file__)))
    sys.path[:] = [path for path in sys.path if os.path.normcase(path) != self_path]

    with_site_packages = os.getenv("PDM_WITH_SITE_PACKAGES")
    needs_user_site = False
    needs_site_packages = False

    if getattr(sys, "argv", None) is None:
        warnings.warn(
            "PEP 582 can't be loaded based on the script path. "
            "As Python 2.7 reached the end of life on 2020/01/01, "
            "please upgrade to Python 3.",
        )
    else:
        script_path = os.path.realpath(sys.argv[0])
        needs_user_site = os.path.normcase(script_path).startswith(
            os.path.normcase(site.USER_BASE)
        )
        needs_site_packages = any(
            os.path.normcase(script_path).startswith(os.path.normcase(p))
            for p in site.PREFIXES
        )

    libpath = get_pypackages_path()
    if not libpath:
        return
    # First, drop site related paths.
    original_sys_path = sys.path[:]
    paths_to_remove = set()
    if not (with_site_packages or needs_user_site):
        site.addusersitepackages(paths_to_remove)
    if not (with_site_packages or needs_site_packages):
        site.addsitepackages(paths_to_remove)
    paths_to_remove = set(os.path.normcase(path) for path in paths_to_remove)
    original_sys_path = [
        path
        for path in original_sys_path
        if os.path.normcase(path) not in paths_to_remove
    ]
    sys.path[:] = original_sys_path

    # Second, add lib directories, ensuring .pth file are processed.
    site.addsitedir(libpath)


main()
del main
