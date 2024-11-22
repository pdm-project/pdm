from __future__ import annotations

import collections
import dataclasses
import os
from functools import cached_property
from pathlib import Path
from typing import Any, Callable, ClassVar, Iterator, Mapping, MutableMapping, cast

import platformdirs
import rich.theme
import tomlkit

from pdm import termui
from pdm._types import RepositoryConfig
from pdm.exceptions import NoConfigError, PdmUsageError

REPOSITORY = "repository"
SOURCE = "pypi"
DEFAULT_REPOSITORIES = {
    "pypi": "https://upload.pypi.org/legacy/",
    "testpypi": "https://test.pypi.org/legacy/",
}

ui = termui.UI()


def load_config(file_path: Path) -> dict[str, Any]:
    """Load a nested TOML document into key-value pairs

    E.g. ["python"]["use_venv"] will be loaded as "python.use_venv" key.
    """

    def get_item(sub_data: Mapping[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for k, v in sub_data.items():
            if k in (REPOSITORY, SOURCE):
                result.update((f"{k}.{sub_k}", sub_v) for sub_k, sub_v in v.items())
            elif isinstance(v, Mapping):
                result.update({f"{k}.{sub_k}": sub_v for sub_k, sub_v in get_item(v).items()})
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

    return bool(val) and val.lower() not in ("false", "no", "0")


def split_by_comma(val: list[str] | str) -> list[str]:
    """Split a string value by comma"""
    if isinstance(val, str):
        return [v.strip() for v in val.split(",")]
    return val


DEFAULT_PYPI_INDEX = "https://pypi.org/simple"


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
    env_var: str | None = None
    coerce: Callable = str
    replace: str | None = None

    def should_show(self) -> bool:
        return self.default is not self._NOT_SET


class Config(MutableMapping[str, str]):
    """A dict-like object for configuration key and values"""

    _config_map: ClassVar[dict[str, ConfigItem]] = {
        "cache_dir": ConfigItem(
            "The root directory of cached files",
            platformdirs.user_cache_dir("pdm"),
            True,
            env_var="PDM_CACHE_DIR",
        ),
        "log_dir": ConfigItem(
            "The root directory of log files",
            platformdirs.user_log_dir("pdm"),
            True,
            env_var="PDM_LOG_DIR",
        ),
        "check_update": ConfigItem(
            "Check if there is any newer version available",
            True,
            True,
            env_var="PDM_CHECK_UPDATE",
            coerce=ensure_boolean,
        ),
        "build_isolation": ConfigItem(
            "Isolate build environment from the project environment",
            True,
            False,
            "PDM_BUILD_ISOLATION",
            ensure_boolean,
        ),
        "request_timeout": ConfigItem(
            "The timeout for network requests in seconds", 15, True, "PDM_REQUEST_TIMEOUT", coerce=int
        ),
        "use_uv": ConfigItem(
            "Use uv for faster resolution and installation",
            False,
            False,
            "PDM_USE_UV",
            ensure_boolean,
        ),
        "global_project.fallback": ConfigItem(
            "Use the global project implicitly if no local project is found",
            False,
            True,
            coerce=ensure_boolean,
        ),
        "global_project.fallback_verbose": ConfigItem(
            "If True show message when global project is used implicitly",
            True,
            True,
            coerce=ensure_boolean,
        ),
        "global_project.path": ConfigItem(
            "The path to the global project",
            platformdirs.user_config_path("pdm") / "global-project",
            True,
        ),
        "global_project.user_site": ConfigItem("Whether to install to user site", False, True, coerce=ensure_boolean),
        "strategy.update": ConfigItem("The default strategy for updating packages", "reuse", False),
        "strategy.save": ConfigItem("Specify how to save versions when a package is added", "minimum", False),
        "strategy.resolve_max_rounds": ConfigItem(
            "Specify the max rounds of resolution process",
            10000,
            env_var="PDM_RESOLVE_MAX_ROUNDS",
            coerce=int,
        ),
        "strategy.inherit_metadata": ConfigItem(
            "Inherit the groups and markers from parents for each package", True, coerce=ensure_boolean
        ),
        "install.parallel": ConfigItem(
            "Whether to perform installation and uninstallation in parallel",
            True,
            env_var="PDM_INSTALL_PARALLEL",
            coerce=ensure_boolean,
        ),
        "install.cache": ConfigItem(
            "Cache wheel installation and only put symlinks in the library root",
            False,
            coerce=ensure_boolean,
        ),
        "install.cache_method": ConfigItem(
            "Specify how to create links to the caches(`symlink/hardlink`)",
            "symlink",
        ),
        "python.providers": ConfigItem(
            "List of python provider names for findpython", default=[], coerce=split_by_comma
        ),
        "python.use_pyenv": ConfigItem("Use the pyenv interpreter", True, coerce=ensure_boolean),
        "python.use_venv": ConfigItem(
            "Use virtual environments when available", True, env_var="PDM_USE_VENV", coerce=ensure_boolean
        ),
        "python.install_root": ConfigItem(
            "The root directory to install python interpreters",
            global_only=True,
            default=os.path.join(platformdirs.user_data_dir("pdm"), "python"),
        ),
        "pypi.url": ConfigItem(
            "The URL of PyPI mirror, defaults to https://pypi.org/simple",
            DEFAULT_PYPI_INDEX,
            env_var="PDM_PYPI_URL",
        ),
        "pypi.verify_ssl": ConfigItem(
            "Verify SSL certificate when query PyPI",
            True,
            env_var="PDM_PYPI_VERIFY_SSL",
            coerce=ensure_boolean,
        ),
        "pypi.username": ConfigItem("The username to access PyPI", env_var="PDM_PYPI_USERNAME"),
        "pypi.password": ConfigItem("The password to access PyPI", env_var="PDM_PYPI_PASSWORD"),
        "pypi.ca_certs": ConfigItem(
            "Path to a CA certificate bundle used for verifying the identity of the PyPI server", global_only=True
        ),
        "pypi.ignore_stored_index": ConfigItem(
            "Don't add the indexes from the config that is not listed in project",
            False,
            env_var="PDM_IGNORE_STORED_INDEX",
            coerce=ensure_boolean,
        ),
        "pypi.client_cert": ConfigItem("Path to client certificate file, or combined cert/key file", global_only=True),
        "pypi.client_key": ConfigItem("Path to client cert keyfile, if not in pypi.client_cert", global_only=True),
        "pypi.json_api": ConfigItem(
            "Consult PyPI's JSON API for package metadata",
            False,
            env_var="PDM_PYPI_JSON_API",
            coerce=ensure_boolean,
        ),
        "venv.location": ConfigItem(
            "Parent directory for virtualenvs",
            os.path.join(platformdirs.user_data_dir("pdm"), "venvs"),
            global_only=True,
        ),
        "venv.backend": ConfigItem(
            "Default backend to create virtualenv",
            default="virtualenv",
            env_var="PDM_VENV_BACKEND",
        ),
        "venv.in_project": ConfigItem(
            "Create virtualenv in `.venv` under project root",
            default=True,
            env_var="PDM_VENV_IN_PROJECT",
            coerce=ensure_boolean,
        ),
        "venv.prompt": ConfigItem(
            "Define a custom template to be displayed in the prompt when virtualenv is"
            "active. Variables `project_name` and `python_version` are available for"
            "formatting",
            default="{project_name}-{python_version}",
            env_var="PDM_VENV_PROMPT",
        ),
        "venv.with_pip": ConfigItem(
            "Install pip when creating a new venv",
            default=False,
            env_var="PDM_VENV_WITH_PIP",
            coerce=ensure_boolean,
        ),
    }
    _config_map.update(
        (f"theme.{k}", ConfigItem(f"Theme color for {k}", default=v, global_only=True))
        for k, v in termui.DEFAULT_THEME.items()
    )

    site: Config | None = None

    @classmethod
    def get_defaults(cls) -> dict[str, Any]:
        defaults = {k: v.default for k, v in cls._config_map.items() if v.should_show()}
        if cls.site is None:
            cls.site = Config(platformdirs.site_config_path("pdm") / "config.toml")
        defaults.update(cls.site.self_data)
        return defaults

    @cached_property
    def env_map(self) -> Mapping[str, Any]:
        return EnvMap(self._config_map)

    @classmethod
    def add_config(cls, name: str, item: ConfigItem) -> None:
        """Add or modify a config item"""
        cls._config_map[name] = item

    def __init__(self, config_file: Path, is_global: bool = False):
        self.is_global = is_global
        self.config_file = config_file.resolve()
        self.deprecated = {v.replace: k for k, v in self._config_map.items() if v.replace}
        self._file_data = load_config(self.config_file)
        self._data = collections.ChainMap(
            cast(MutableMapping[str, Any], self.env_map) if not is_global else {},
            self._file_data,
            self.get_defaults() if is_global else {},
        )

    def load_theme(self) -> rich.theme.Theme:
        if not self.is_global:  # pragma: no cover
            raise PdmUsageError("Theme can only be loaded from global config")
        return rich.theme.Theme({k[6:]: v for k, v in self.items() if k.startswith("theme.")})

    @property
    def self_data(self) -> dict[str, Any]:
        return dict(self._file_data)

    def iter_sources(self) -> Iterator[RepositoryConfig]:
        for name, data in self._data.items():
            if name.startswith(f"{SOURCE}.") and name not in self._config_map and data:
                yield RepositoryConfig(**data, name=name[len(SOURCE) + 1 :], config_prefix=SOURCE)

    def _save_config(self) -> None:
        """Save the changed to config file."""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        toml_data: dict[str, Any] = {}
        for key, value in self._file_data.items():
            *parts, last = key.split(".")
            temp = toml_data
            for part in parts:
                if part not in temp:
                    temp[part] = {}
                temp = temp[part]
            temp[last] = value

        with self.config_file.open("w", encoding="utf-8") as fp:
            tomlkit.dump(toml_data, fp)

    def __getitem__(self, key: str) -> Any:
        parts = key.split(".")
        if parts[0] in (REPOSITORY, SOURCE) and key not in self._config_map:
            if len(parts) < 2:
                raise PdmUsageError(f"Must specify a {parts[0]} name")
            repo = self.get_repository_config(parts[1], parts[0])
            if repo is None:
                raise KeyError(f"No {parts[0]} named {parts[1]}")

            value = getattr(repo, parts[2]) if len(parts) >= 3 else repo
            return value

        if key not in self._config_map and key not in self.deprecated:
            raise NoConfigError(key)
        config_key = self.deprecated.get(key, key)
        config = self._config_map[config_key]

        if config_key in self._data:
            result = self._data[config_key]
        elif config.replace:
            result = self._data[config.replace]
        else:
            raise NoConfigError(key) from None
        return config.coerce(result)

    def __setitem__(self, key: str, value: Any) -> None:
        from pdm.models.auth import keyring

        parts = key.split(".")
        if parts[0] in (REPOSITORY, SOURCE) and key not in self._config_map:
            if len(parts) < 3:
                raise PdmUsageError(f"Set {parts[0]} config with [success]{parts[0]}.{{name}}.{{attr}}")
            index_key = ".".join(parts[:2])
            username = self._data.get(index_key, {}).get("username")  # type: ignore[call-overload]
            service = f'pdm-{index_key.replace(".", "-")}'
            if (
                parts[2] == "password"
                and self.is_global
                and username
                and keyring.save_auth_info(service, username, value)
            ):
                return
            if parts[2] == "verify_ssl":
                value = ensure_boolean(value)
            self._file_data.setdefault(index_key, {})[parts[2]] = value
            self._save_config()
            return

        if key not in self._config_map and key not in self.deprecated:
            raise NoConfigError(key)
        config_key = self.deprecated.get(key, key)
        config = self._config_map[config_key]
        if not self.is_global and config.global_only:
            raise ValueError(f"Config item '{key}' is not allowed to set in project config.")

        value = config.coerce(value)
        if key in self.env_map:
            ui.warn(f"the config is shadowed by env var '{config.env_var}', the value set won't take effect.")
        self._file_data[config_key] = value
        if config.replace:
            self._file_data.pop(config.replace, None)
        self._save_config()

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self) -> Iterator[str]:
        keys: set[str] = set()
        for key in self._data:
            if key in self.deprecated:
                key = self.deprecated[key]
            keys.add(key)
        return iter(keys)

    def __delitem__(self, key: str) -> None:
        from pdm.models.auth import keyring

        parts = key.split(".")
        if parts[0] in (REPOSITORY, SOURCE) and key not in self._config_map:
            if len(parts) < 2:
                raise PdmUsageError(f"Should specify the name of {parts[0]}")
            index_key = ".".join(parts[:2])
            username = self._data.get(index_key, {}).get("username")  # type: ignore[call-overload]
            service = f'pdm-{index_key.replace(".", "-")}'
            if len(parts) >= 3:
                index_key, attr = key.rsplit(".", 1)
                if attr == "password" and username:
                    keyring.delete_auth_info(service, username)
                self._file_data.get(index_key, {}).pop(attr, None)
            else:
                del self._file_data[key]
                if username:
                    keyring.delete_auth_info(service, username)
            self._save_config()
            return

        config_key = self.deprecated.get(key, key)
        config = self._config_map[config_key]
        self._file_data.pop(config_key, None)
        if config.replace:
            self._file_data.pop(config.replace, None)

        env_var = config.env_var
        if env_var is not None and env_var in os.environ:
            ui.warn(f"The config is shadowed by env var '{env_var}', set value won't take effect.")
        self._save_config()

    def get_repository_config(self, name_or_url: str, prefix: str) -> RepositoryConfig | None:
        """Get a repository or source by name or url."""
        if not self.is_global and prefix == REPOSITORY:  # pragma: no cover
            raise NoConfigError(prefix)
        repositories: dict[str, RepositoryConfig] = {}
        for k, v in self._data.items():
            if not k.startswith(f"{prefix}.") or k in self._config_map:
                continue
            key = k[len(prefix) + 1 :]
            repositories[key] = RepositoryConfig(**v, name=key, config_prefix=prefix)
        config: RepositoryConfig | None = None
        if "://" in name_or_url:
            config = next(
                (v for v in repositories.values() if v.url == name_or_url),
                RepositoryConfig(url=name_or_url, name="__unknown__", config_prefix=prefix),
            )
        else:
            config = repositories.get(name_or_url)

        if prefix == SOURCE:
            return config

        if name_or_url in DEFAULT_REPOSITORIES:
            if config is None:
                return RepositoryConfig(url=DEFAULT_REPOSITORIES[name_or_url], name=name_or_url, config_prefix=prefix)
            config.passive_update(url=DEFAULT_REPOSITORIES[name_or_url])
        if name_or_url in DEFAULT_REPOSITORIES.values():
            name = next(k for k, v in DEFAULT_REPOSITORIES.items() if v == name_or_url)
            if config is None:
                return RepositoryConfig(
                    name=name,
                    config_prefix=prefix,
                    url=name_or_url,
                )
            config.passive_update(url=name_or_url)
            if config.name == "__unknown__":
                config.name = name
        return config


class EnvMap(Mapping[str, Any]):
    def __init__(self, config_items: Mapping[str, ConfigItem]) -> None:
        self._config_map = config_items

    def __repr__(self) -> str:
        return repr(dict(self))

    def __getitem__(self, k: str) -> Any:
        try:
            item = self._config_map[k]
            if item.env_var:
                return item.coerce(os.environ[item.env_var])
        except KeyError:
            pass
        raise KeyError(k)

    def __iter__(self) -> Iterator[str]:
        for key, item in self._config_map.items():
            if item.env_var and item.env_var in os.environ:
                yield key

    def __len__(self) -> int:
        return sum(1 for _ in self)
