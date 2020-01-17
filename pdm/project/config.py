from collections.abc import MutableMapping
from pathlib import Path
from typing import Any, Dict, Iterable

import appdirs
import tomlkit
from pdm.exceptions import NoConfigError


class Config(MutableMapping):
    DEFAULT_CONFIG = {
        "cache_dir": appdirs.user_cache_dir("pdm"),
        "python": None,
        "packages_path": None
    }

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self._data = self.DEFAULT_CONFIG.copy()
        self._dirty = {}

        self._project_config_file = self.project_root / ".pdm.toml"
        self._global_config_file = Path(appdirs.user_config_dir("pdm")) / ".pdm.toml"
        self._project_config = self.load_config(self._project_config_file)
        self._global_config = self.load_config(self._global_config_file)
        # First load user config, then project config
        for config in (self._global_config, self._project_config):
            self._data.update(dict(config))

    def load_config(self, file_path: Path) -> Dict[str, Any]:
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

    def save_config(self, is_global: bool = False) -> None:
        data = self._global_config if is_global else self._project_config
        data.update(self._dirty)
        file_path = self._global_config_file if is_global else self._project_config_file
        file_path.parent.mkdir(exist_ok=True)
        toml_data = {}
        for key, value in data.items():
            *parts, last = key.split(".")
            temp = toml_data
            for part in parts:
                temp = temp.setdefault(part, {})
            temp[last] = value

        with file_path.open(encoding="utf-8") as fp:
            fp.write(tomlkit.dumps(toml_data))
        self._dirty.clear()

    def __getitem__(self, key: str) -> Any:
        try:
            return self._data[key]
        except KeyError:
            raise NoConfigError(key) from None

    def __setitem__(self, key: str, value: Any) -> None:
        if key not in self.DEFAULT_CONFIG:
            raise NoConfigError(key)
        self._dirty[key] = value
        self._data[key] = value

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self) -> Iterable[str]:
        return iter(self._data)

    def __delitem__(self, key) -> None:
        raise NotImplementedError
