from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)
# Export for plugin use
from pdm.cli.commands.base import BaseCommand
from pdm.core import Core
from pdm.installers import Installer, Synchronizer
from pdm.project import Config, ConfigItem, Project

__all__ = (
    "Project",
    "Config",
    "ConfigItem",
    "BaseCommand",
    "Installer",
    "Synchronizer",
    "Core",
)


def _fix_pkg_resources():
    import importlib
    import sys

    sys.modules["pkg_resources"] = importlib.import_module("pip._vendor.pkg_resources")


_fix_pkg_resources()
del _fix_pkg_resources


def set_importlib_readonly(mode):
    import os
    import sysconfig

    target = os.path.join(sysconfig.get_path("purelib"), "importlib_metadata")
    if not os.path.exists(target):
        return

    for root, dirs, files in os.walk(target, topdown=False):
        for dir in [os.path.join(root, d) for d in dirs]:
            os.chmod(dir, mode)
        for file in [os.path.join(root, f) for f in files]:
            os.chmod(file, mode)


try:
    set_importlib_readonly(0o555)
except OSError:
    pass
