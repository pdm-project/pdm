import os
import site
import sys


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

    libpath = get_pypackages_path()
    if not libpath:
        return

    # First, drop site related paths.
    original_sys_path = sys.path[:]
    known_paths = set()
    site.addusersitepackages(known_paths)
    site.addsitepackages(known_paths)
    known_paths = set(os.path.normcase(path) for path in known_paths)
    original_sys_path = [
        path for path in original_sys_path if os.path.normcase(path) not in known_paths
    ]
    sys.path[:] = original_sys_path

    # Second, add lib directories, ensuring .pth file are processed.
    site.addsitedir(libpath)
    # Then add the removed path to the tail of the paths
    known_paths.clear()
    site.addusersitepackages(known_paths)
    site.addsitepackages(known_paths)


main()
del main
