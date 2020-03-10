from collections.abc import MutableMapping
from pathlib import Path
from typing import Any, Dict, Iterable

import appdirs
import tomlkit

from pdm.exceptions import NoConfigError
from pdm.utils import get_pypi_source


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


class Config(MutableMapping):
    """A dict-like object for configuration key and values"""

    HOME_CONFIG = Path.home() / ".pdm" / "config.toml"
    CONFIG_ITEMS = {
        # config name: (config_description, not_for_project)
        "cache_dir": ("The root directory of cached files", True),
        "auto_global": (
            "Use global package implicity if no local project is found",
            True,
        ),
        "python.path": ("The Python interpreter path", False),
        "python.use_pyenv": ("Use the pyenv interpreter", False),
        "pypi.url": (
            "The URL of PyPI mirror, defaults to https://pypi.org/simple",
            False,
        ),
        "pypi.verify_ssl": ("Verify SSL certificate when query PyPI", False),
    }
    DEFAULT_CONFIG = {
        "auto_global": False,
        "cache_dir": appdirs.user_cache_dir("pdm"),
        "python.use_pyenv": True,
    }
    DEFAULT_CONFIG.update(get_pypi_source())

    def __init__(self, config_file: Path, is_global: bool = False):
        self._data = {}
        if is_global:
            self._data.update(self.DEFAULT_CONFIG)

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
                temp = temp.setdefault(part, {})
            temp[last] = value

        with self._config_file.open("w", encoding="utf-8") as fp:
            fp.write(tomlkit.dumps(toml_data))

    def __getitem__(self, key: str) -> Any:
        try:
            return self._data[key]
        except KeyError:
            raise NoConfigError(key) from None

    def __setitem__(self, key: str, value: Any) -> None:
        if key not in self.CONFIG_ITEMS:
            raise NoConfigError(key)
        if not self.is_global and self.CONFIG_ITEMS[key][1]:
            raise ValueError(
                f"Config item '{key}' is not allowed to set in project config."
            )
        if isinstance(value, str):
            if value.lower() == "false":
                value = False
            elif value.lower() == "true":
                value = True

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
            self._save_config()
