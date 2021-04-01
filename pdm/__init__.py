from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)  # type: ignore
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


def _fix_pkg_resources() -> None:
    import importlib
    import sys

    sys.modules["pkg_resources"] = importlib.import_module("pip._vendor.pkg_resources")


_fix_pkg_resources()
del _fix_pkg_resources
