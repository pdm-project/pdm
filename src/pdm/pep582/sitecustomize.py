import os
import site
import sys
import sysconfig


def get_pypackages_path():
    def find_pypackage(path):
        for _ in range(int(os.getenv("PDM_PROJECT_MAX_DEPTH", "5"))):
            pypackages = os.path.join(path, "__pypackages__")
            if not os.path.exists(pypackages):
                continue
            lib_path = sysconfig.get_path("purelib", vars={"base": pypackages, "platbase": pypackages})
            if os.path.exists(lib_path):
                return pypackages, lib_path
            if os.path.dirname(path) == path:
                # Root path is reached
                break
            path = os.path.dirname(path)
        return None, None

    if getattr(sys, "argv", None) and sys.argv[0]:
        script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        find_paths = [script_dir]
    else:
        # This is a REPL session
        find_paths = [os.getcwd()]

    for path in find_paths:
        result = find_pypackage(path)
        if result[0] is not None:
            return result
    return None, None


def load_next_sitecustomize_py2():
    import imp

    try:
        f, pathname, desc = imp.find_module("sitecustomize", sys.path)
        try:
            imp.load_module("another_sitecustomize", f, pathname, desc)
        finally:
            f.close()
    except ImportError:
        pass


def load_next_sitecustomize_py3():
    import importlib.util

    old_module = sys.modules.pop("sitecustomize", None)
    spec = importlib.util.find_spec("sitecustomize")
    if spec is not None:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    if old_module is not None:
        sys.modules["sitecustomize"] = old_module


def patch_sysconfig(prefix):
    """This is a hack to make sure that the sysconfig.get_paths()
    returns PEP 582 scheme.
    """
    # This returns a global variable, just update it in place.
    config_vars = sysconfig.get_config_vars()
    config_vars["base"] = config_vars["platbase"] = prefix


def main():
    self_path = os.path.normcase(os.path.dirname(os.path.abspath(__file__)))
    sys.path[:] = [path for path in sys.path if os.path.normcase(path) != self_path]

    if sys.version_info[0] == 2:
        load_next_sitecustomize_py2()
    else:
        load_next_sitecustomize_py3()

    prefix, libpath = get_pypackages_path()
    if not libpath:
        return

    # First, drop site related paths.
    original_sys_path = sys.path[:]
    known_paths = set()
    site.addusersitepackages(known_paths)
    site.addsitepackages(known_paths)
    known_paths = {os.path.normcase(path) for path in known_paths}
    original_sys_path = [path for path in original_sys_path if os.path.normcase(path) not in known_paths]
    sys.path[:] = original_sys_path

    # Second, add lib directories, ensuring .pth file are processed.
    site.addsitedir(libpath)
    if not os.environ.pop("NO_SITE_PACKAGES", None):
        # Then add the removed path to the tail of the paths
        known_paths.clear()
        site.addusersitepackages(known_paths)
        site.addsitepackages(known_paths)

    patch_sysconfig(prefix)


main()
del main
