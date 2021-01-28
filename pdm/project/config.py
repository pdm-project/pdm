import dataclasses
import os
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional, TypeVar

import appdirs
import tomlkit

from pdm.exceptions import NoConfigError
from pdm.iostream import stream
from pdm.utils import get_pypi_source

T = TypeVar("T")


def load_config(file_path: Path) -> Dict[str, Any]:
    """Load a nested TOML document into key-value paires

    E.g. ["python"]["path"] will be loaded as "python.path" key.
    """

    def get_item(sub_data):
        result = {}
        for k, v in sub_data.items():
            if getattr(v, "items", None) is not None:
                result.update(
                    {f"{k}.{sub_k}": sub_v for sub_k, sub_v in get_item(v).items()}
                )
            else:
                result.update({k: v})
        return result

    if not file_path.is_file():
        return {}
    return get_item(dict(tomlkit.parse(file_path.read_text("utf-8"))))


def ensure_boolean(val: Any) -> bool:
    """Coerce a string value to a boolean value"""
    if not isinstance(val, str):
        return val

    return val and val.lower() not in ("false", "no", "0")


@dataclasses.dataclass
class ConfigItem:
    """An item of configuration, with following attributes:

    - description: the config description
    - default: the default value, if given, will show in `pdm config`
    - global_only: not allowed to save in project config
    - env_var: the env var name to take value from
    """

    _NOT_SET = object()

    description: str
    default: Any = _NOT_SET
    global_only: bool = False
    env_var: Optional[str] = None
    coerce: Callable[[Any], Any] = str

    def should_show(self) -> bool:
        return self.default is not self._NOT_SET


class Config(MutableMapping):
    """A dict-like object for configuration key and values"""

    HOME_CONFIG = Path.home() / ".pdm" / "config.toml"

    pypi_url, verify_ssl = get_pypi_source()
    _config_map = {
        "cache_dir": ConfigItem(
            "The root directory of cached files", appdirs.user_cache_dir("pdm"), True
        ),
        "auto_global": ConfigItem(
            "Use global package implicity if no local project is found",
            False,
            True,
            "PDM_AUTO_GLOBAL",
            coerce=ensure_boolean,
        ),
        "strategy.update": ConfigItem(
            "The default strategy for updating packages", "reuse", False
        ),
        "strategy.save": ConfigItem(
            "Specify how to save versions when a package is added", "compatible", False
        ),
        "strategy.resolve_max_rounds": ConfigItem(
            "Specify the max rounds of resolution process",
            1000,
            env_var="PDM_RESOLVE_MAX_ROUDNS",
            coerce=int,
        ),
        "parallel_install": ConfigItem(
            "Whether to perform installation and uninstallation in parallel",
            True,
            env_var="PDM_PARALLEL_INSTALL",
            coerce=ensure_boolean,
        ),
        "python.path": ConfigItem("The Python interpreter path", env_var="PDM_PYTHON"),
        "python.use_pyenv": ConfigItem(
            "Use the pyenv interpreter", True, coerce=ensure_boolean
        ),
        "pypi.url": ConfigItem(
            "The URL of PyPI mirror, defaults to https://pypi.org/simple",
            pypi_url,
            env_var="PDM_PYPI_URL",
        ),
        "pypi.verify_ssl": ConfigItem(
            "Verify SSL certificate when query PyPI", verify_ssl, coerce=ensure_boolean
        ),
        "pypi.json_api": ConfigItem(
            "Consult PyPI's JSON API for package metadata",
            False,
            env_var="PDM_PYPI_JSON_API",
            coerce=ensure_boolean,
        ),
        "use_venv": ConfigItem(
            "Install packages into the activated venv site packages instead of PEP 582",
            False,
            env_var="PDM_USE_VENV",
            coerce=ensure_boolean,
        ),
    }  # type: Dict[str, ConfigItem]
    del pypi_url, verify_ssl

    @classmethod
    def get_defaults(cls):
        return {k: v.default for k, v in cls._config_map.items() if v.should_show()}

    @classmethod
    def add_config(cls, name: str, item: ConfigItem) -> None:
        """Add or modify a config item"""
        cls._config_map[name] = item

    def __init__(self, config_file: Path, is_global: bool = False):
        self._data = {}
        if is_global:
            self._data.update(self.get_defaults())

        self.is_global = is_global
        self._config_file = config_file
        self._file_data = load_config(self._config_file)
        self._data.update(self._file_data)

    def _save_config(self) -> None:
        """Save the changed to config file."""
        self._config_file.parent.mkdir(parents=True, exist_ok=True)
        toml_data = {}
        for key, value in self._file_data.items():
            *parts, last = key.split(".")
            temp = toml_data
            for part in parts:
                if part not in temp:
                    temp[part] = {}
                temp = temp[part]
            temp[last] = value

        with self._config_file.open("w", encoding="utf-8") as fp:
            fp.write(tomlkit.dumps(toml_data))

    def __getitem__(self, key: str) -> Any:
        env_var = self._config_map[key].env_var
        if env_var is not None and env_var in os.environ:
            result = os.environ[env_var]
        else:
            try:
                result = self._data[key]
            except KeyError:
                raise NoConfigError(key) from None
        return self._config_map[key].coerce(result)

    def __setitem__(self, key: str, value: Any) -> None:
        if key not in self._config_map:
            raise NoConfigError(key)
        if not self.is_global and self._config_map[key].global_only:
            raise ValueError(
                f"Config item '{key}' is not allowed to set in project config."
            )

        value = self._config_map[key].coerce(value)
        env_var = self._config_map[key].env_var
        if env_var is not None and env_var in os.environ:
            stream.echo(
                stream.yellow(
                    "WARNING: the config is shadowed by env var '{}', "
                    "the value set won't take effect.".format(env_var)
                )
            )
        self._data[key] = value
        self._file_data[key] = value
        self._save_config()

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self) -> Iterable[str]:
        return iter(self._data)

    def __delitem__(self, key) -> None:
        self._data.pop(key, None)
        try:
            del self._file_data[key]
        except KeyError:
            pass
        else:
            env_var = self._config_map[key].env_var
            if env_var is not None and env_var in os.environ:
                stream.echo(
                    stream.yellow(
                        "WARNING: the config is shadowed by env var '{}', "
                        "set value won't take effect.".format(env_var)
                    )
                )
            self._save_config()
