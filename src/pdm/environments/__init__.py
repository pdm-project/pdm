from typing import Any

from pdm.environments.base import BareEnvironment, BaseEnvironment
from pdm.environments.local import PythonLocalEnvironment
from pdm.environments.python import PythonEnvironment
from pdm.utils import deprecation_warning

_deprecated = {"Environment": PythonLocalEnvironment, "GlobalEnvironment": PythonEnvironment}


def __getattr__(name: str) -> Any:
    if name in _deprecated:
        real = _deprecated[name]
        deprecation_warning(f"{name} is deprecated, please use {real.__name__} instead", stacklevel=2)
        return real
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "BaseEnvironment",
    "BareEnvironment",
    "PythonEnvironment",
    "PythonLocalEnvironment",
]
__all__.extend(_deprecated)
