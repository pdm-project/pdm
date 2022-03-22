import dataclasses
import os
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, MutableMapping, Optional, Set, TypeVar

import click
import platformdirs
import tomlkit

from pdm import termui
from pdm.exceptions import NoConfigError
from pdm.utils import get_pypi_source

T = TypeVar("T")


def load_config(file_path: Path) -> Dict[str, Any]:
    """Load a nested TOML document into key-value paires

    E.g. ["python"]["path"] will be loaded as "python.path" key.
    """

    def get_item(sub_data: Dict[str, Any]) -> Dict[str, Any]:
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
    return get_item(dict(tomlkit.parse(file_path.read_text("utf-8"))))  # type: ignore


def ensure_boolean(val: Any) -> bool:
    """Coerce a string value to a boolean value"""
    if not isinstance(val, str):
        return val

    return bool(val) and val.lower() not in ("false", "no", "0")


@dataclasses.dataclass
class ConfigItem:
    """An item of configuration, with following attributes:

    Args:
        description (str): the config description
        default (Any): the default value, if given, will show in `pdm config`
        global_only (bool): not allowed to save in project config
        env_var (str|None): the env var name to take value from
        coerce (Callable): a function to coerce the value
        replace: (str|None): the deprecated name to replace
    """

    _NOT_SET = object()

    description: str
    default: Any = _NOT_SET
    global_only: bool = False
    env_var: Optional[str] = None
    coerce: Callable = str
    replace: Optional[str] = None

    def should_show(self) -> bool:
        return self.default is not self._NOT_SET


class Config(MutableMapping[str, str]):
    """A dict-like object for configuration key and values"""

    pypi_url, verify_ssl = get_pypi_source()
    _config_map: Dict[str, ConfigItem] = {
        "cache_dir": ConfigItem(
            "The root directory of cached files",
            platformdirs.user_cache_dir("pdm"),
            True,
        ),
        "check_update": ConfigItem(
            "Check if there is any newer version available",
            True,
            True,
            coerce=ensure_boolean,
        ),
        "build_isolation": ConfigItem(
            "Isolate build environment from the project environment",
            True,
            False,
            "PDM_BUILD_ISOLATION",
            ensure_boolean,
        ),
        "global_project.fallback": ConfigItem(
            "Use the global project implicitly if no local project is found",
            False,
            True,
            coerce=ensure_boolean,
            replace="auto_global",
        ),
        "global_project.path": ConfigItem(
            "The path to the global project",
            os.path.expanduser("~/.pdm/global-project"),
            True,
        ),
        "global_project.user_site": ConfigItem(
            "Whether to install to user site", False, True, coerce=ensure_boolean
        ),
        "project_max_depth": ConfigItem(
            "The max depth to search for a project through the parents",
            5,
            True,
            env_var="PDM_PROJECT_MAX_DEPTH",
            coerce=int,
        ),
        "strategy.update": ConfigItem(
            "The default strategy for updating packages", "reuse", False
        ),
        "strategy.save": ConfigItem(
            "Specify how to save versions when a package is added", "minimum", False
        ),
        "strategy.resolve_max_rounds": ConfigItem(
            "Specify the max rounds of resolution process",
            10000,
            env_var="PDM_RESOLVE_MAX_ROUDNS",
            coerce=int,
        ),
        "install.parallel": ConfigItem(
            "Whether to perform installation and uninstallation in parallel",
            True,
            env_var="PDM_INSTALL_PARALLEL",
            coerce=ensure_boolean,
            replace="parallel_install",
        ),
        "install.cache": ConfigItem(
            "Cache wheel installation and only put symlinks in the library root",
            False,
            coerce=ensure_boolean,
            replace="feature.install_cache",
        ),
        "install.cache_method": ConfigItem(
            "`symlink` or `pth` to create links to the cached installation",
            "symlink",
            replace="feature.install_cache_method",
        ),
        "python.path": ConfigItem("The Python interpreter path", env_var="PDM_PYTHON"),
        "python.use_pyenv": ConfigItem(
            "Use the pyenv interpreter", True, coerce=ensure_boolean
        ),
        "python.use_venv": ConfigItem(
            "Install packages into the activated venv site packages instead of PEP 582",
            False,
            env_var="PDM_USE_VENV",
            coerce=ensure_boolean,
            replace="use_venv",
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
    }
    del pypi_url, verify_ssl

    @classmethod
    def get_defaults(cls) -> Dict[str, Any]:
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
        self._config_file = config_file.resolve()
        self._file_data = load_config(self._config_file)
        self.deprecated = {
            v.replace: k for k, v in self._config_map.items() if v.replace
        }
        self._data.update(self._file_data)

    def _save_config(self) -> None:
        """Save the changed to config file."""
        self._config_file.parent.mkdir(parents=True, exist_ok=True)
        toml_data: Dict[str, Any] = {}
        for key, value in self._file_data.items():
            *parts, last = key.split(".")
            temp = toml_data
            for part in parts:
                if part not in temp:
                    temp[part] = {}
                temp = temp[part]
            temp[last] = value

        with self._config_file.open("w", encoding="utf-8") as fp:
            tomlkit.dump(toml_data, fp)  # type: ignore

    def __getitem__(self, key: str) -> Any:
        if key not in self._config_map and key not in self.deprecated:
            raise NoConfigError(key)
        config_key = self.deprecated.get(key, key)
        config = self._config_map[config_key]
        env_var = config.env_var
        if env_var is not None and env_var in os.environ:
            result = os.environ[env_var]
        else:
            if config_key in self._data:
                result = self._data[config_key]
            elif config.replace:
                result = self._data[config.replace]
            else:
                raise NoConfigError(key) from None
        return config.coerce(result)

    def __setitem__(self, key: str, value: Any) -> None:
        if key not in self._config_map and key not in self.deprecated:
            raise NoConfigError(key)
        config_key = self.deprecated.get(key, key)
        config = self._config_map[config_key]
        if not self.is_global and config.global_only:
            raise ValueError(
                f"Config item '{key}' is not allowed to set in project config."
            )

        value = config.coerce(value)
        env_var = config.env_var
        if env_var is not None and env_var in os.environ:
            click.echo(
                termui.yellow(
                    "WARNING: the config is shadowed by env var '{}', "
                    "the value set won't take effect.".format(env_var)
                )
            )
        self._data[config_key] = value
        self._file_data[config_key] = value
        if config.replace:
            self._data.pop(config.replace, None)
            self._file_data.pop(config.replace, None)
        self._save_config()

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self) -> Iterator[str]:
        keys: Set[str] = set()
        for key in self._data:
            if key in self._config_map:
                keys.add(key)
            elif key in self.deprecated:
                keys.add(self.deprecated[key])
        return iter(keys)

    def __delitem__(self, key: str) -> None:
        config_key = self.deprecated.get(key, key)
        config = self._config_map[config_key]
        self._data.pop(config_key, None)
        self._file_data.pop(config_key, None)
        if self.is_global and config.should_show():
            self._data[config_key] = config.default
        if config.replace:
            self._data.pop(config.replace, None)
            self._file_data.pop(config.replace, None)

        env_var = config.env_var
        if env_var is not None and env_var in os.environ:
            click.echo(
                termui.yellow(
                    "WARNING: the config is shadowed by env var '{}', "
                    "set value won't take effect.".format(env_var)
                )
            )
        self._save_config()
