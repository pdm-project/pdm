from typing import Any

from pdm.environments.base import BareEnvironment, BaseEnvironment
from pdm.environments.local import PythonLocalEnvironment
from pdm.environments.prefix import PrefixEnvironment
from pdm.environments.python import PythonEnvironment

_deprecated = {"Environment": PythonLocalEnvironment, "GlobalEnvironment": PythonEnvironment}


def __getattr__(name: str) -> Any:
    if name in _deprecated:
        import warnings

        real = _deprecated[name]
        warnings.warn(
            f"{name} is deprecated, please use {real.__name__} instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return real
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "BaseEnvironment",
    "BareEnvironment",
    "PythonEnvironment",
    "PrefixEnvironment",
    "PythonLocalEnvironment",
]
__all__.extend(_deprecated)
