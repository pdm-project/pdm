import os
import site
import sys
from pathlib import Path


def get_pypackages_path():
    def find_pypackage(path, version):
        if not path.exists():
            return None

        packages_name = f"__pypackages__/{version}/lib"
        files = list(path.glob(packages_name))
        if files:
            return str(files[0])

        if path == path.parent:
            return None

        return find_pypackage(path.parent, version)

    if "PEP582_PACKAGES" in os.environ:
        return os.path.join(os.getenv("PEP582_PACKAGES"), "lib")
    find_paths = [os.getcwd()]
    version = bare_version = ".".join(map(str, sys.version_info[:2]))
    if os.name == "nt" and sys.maxsize <= 2**32:
        version += "-32"

    if getattr(sys, "argv", None) and sys.argv[0]:
        script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        find_paths.insert(0, script_dir)

    for path in find_paths:
        result = find_pypackage(Path(path), version)
        if result:
            return result

    if bare_version != version:
        for path in find_paths:
            result = find_pypackage(Path(path), bare_version)
            if result:
                return result


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


def patch_sysconfig(libpath):
    """This is a hack to make sure that the sysconfig.get_paths()
    returns PEP 582 scheme.
    """
    import functools
    import sysconfig

    bin_prefix = "Scripts" if os.name == "nt" else "bin"
    pep582_base = os.path.dirname(libpath)
    pep582_scheme = {
        "stdlib": "{pep582_base}/lib",
        "platstdlib": "{pep582_base}/lib",
        "purelib": "{pep582_base}/lib",
        "platlib": "{pep582_base}/lib",
        "include": "{pep582_base}/include",
        "scripts": f"{{pep582_base}}/{bin_prefix}",
        "data": "{pep582_base}",
        "prefix": "{pep582_base}",
        "headers": "{pep582_base}/include",
    }

    def patch_pep582(get_paths):
        @functools.wraps(get_paths)
        def wrapper(scheme=None, vars=None, expand=True):
            default_scheme = get_paths.__defaults__[0]
            if not vars and scheme is None:
                scheme = "pep582"
            else:
                scheme = scheme or default_scheme
            return get_paths(scheme, vars, expand)

        return wrapper

    # This returns a global variable, just update it in place.
    sysconfig.get_config_vars()["pep582_base"] = pep582_base
    sysconfig.get_paths = patch_pep582(sysconfig.get_paths)
    sysconfig._INSTALL_SCHEMES["pep582"] = pep582_scheme


def main():
    self_path = os.path.normcase(os.path.dirname(os.path.abspath(__file__)))
    sys.path[:] = [path for path in sys.path if os.path.normcase(path) != self_path]

    if sys.version_info[0] == 2:  # noqa: UP036
        load_next_sitecustomize_py2()
    else:
        load_next_sitecustomize_py3()

    libpath = get_pypackages_path()
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
    if "PEP582_PACKAGES" in os.environ:
        patch_sysconfig(libpath)


main()
del main
