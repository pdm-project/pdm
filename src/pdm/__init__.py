import warnings
from pkgutil import extend_path
from typing import Any

__path__ = extend_path(__path__, __name__)  # type: ignore
# Export for plugin use
from pdm.cli.commands.base import BaseCommand as _BaseCommand
from pdm.core import Core as _Core
from pdm.installers import InstallManager as _InstallManager
from pdm.installers import Synchronizer as _Synchronizer
from pdm.project import Config as _Config
from pdm.project import ConfigItem as _ConfigItem
from pdm.project import Project as _Project

_deprecated = {
    "Project": (_Project, "pdm.project"),
    "Config": (_Config, "pdm.project"),
    "ConfigItem": (_ConfigItem, "pdm.project"),
    "BaseCommand": (_BaseCommand, "pdm.cli.commands.base"),
    "InstallManager": (_InstallManager, "pdm.installers"),
    "Synchronizer": (_Synchronizer, "pdm.installers"),
    "Core": (_Core, "pdm.core"),
}

__all__ = tuple(_deprecated)


def __getattr__(name: str) -> Any:
    if name in _deprecated:
        obj, module = _deprecated[name]
        warnings.warn(
            f"Deprecating top-level `from pdm import {name}`. "
            f"Import it from {module} instead."
        )
        return obj
    raise AttributeError(name)
