from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)


def _fix_pkg_resources():
    import importlib
    import sys

    sys.modules["pkg_resources"] = importlib.import_module("pip._vendor.pkg_resources")


_fix_pkg_resources()
del _fix_pkg_resources
