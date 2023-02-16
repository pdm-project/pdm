from __future__ import annotations

import collections
import dataclasses
import os
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, MutableMapping, cast

import platformdirs
import rich.theme
import tomlkit

from pdm import termui
from pdm._types import Source
from pdm.exceptions import NoConfigError, PdmUsageError

ui = termui.UI()

REPOSITORY = "repository"


@dataclasses.dataclass
class RepositoryConfig:
    url: str
    username: str | None = None
    password: str | None = None
    ca_certs: str | None = None

    config_prefix: str | None = None

    def __rich__(self) -> str:
        config_prefix = f"{self.config_prefix}." if self.config_prefix is not None else ""
        lines = [f"[primary]{config_prefix}url[/] = {self.url}"]
        if self.username:
            lines.append(f"[primary]{config_prefix}username[/] = {self.username}")
        if self.password:
            lines.append(f"[primary]{config_prefix}password[/] = [i]<hidden>[/]")
        if self.ca_certs:
            lines.append(f"[primary]{config_prefix}ca_certs[/] = {self.ca_certs}")
        return "\n".join(lines)


@dataclasses.dataclass
class RegistryConfig:
    url: str
    username: str | None = None
    password: str | None = None
    verify_ssl: bool | None = None
    type: str | None = None

    config_prefix: str | None = None

    def __rich__(self) -> str:
        config_prefix = f"{self.config_prefix}." if self.config_prefix is not None else ""
        lines = [f"[primary]{config_prefix}url[/] = {self.url}"]
        if self.username:
            lines.append(f"[primary]{config_prefix}username[/] = {self.username}")
        if self.password:
            lines.append(f"[primary]{config_prefix}password[/] = [i]<hidden>[/]")
        if self.verify_ssl:
            lines.append(f"[primary]{config_prefix}verify_ssl[/] = {self.verify_ssl}")
        if self.type:
            lines.append(f"[primary]{config_prefix}type[/] = {self.type}")
        return "\n".join(lines)


DEFAULT_REPOSITORIES = {
    "pypi": RepositoryConfig("https://upload.pypi.org/legacy/"),
    "testpypi": RepositoryConfig("https://test.pypi.org/legacy/"),
}


def load_config(file_path: Path) -> dict[str, Any]:
    """Load a nested TOML document into key-value pairs

    E.g. ["python"]["path"] will be loaded as "python.path" key.
    """

    def get_item(sub_data: Mapping[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for k, v in sub_data.items():
            if k == "pypi":
                result.update((f"{k}.{sub_k}", sub_v) for sub_k, sub_v in v.items())
            elif k != REPOSITORY and isinstance(v, Mapping):
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

    _config_map: dict[str, ConfigItem] = {
        "cache_dir": ConfigItem(
            "The root directory of cached files",
            platformdirs.user_cache_dir("pdm"),
            True,
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
        "project_max_depth": ConfigItem(
            "The max depth to search for a project through the parents",
            5,
            True,
            env_var="PDM_PROJECT_MAX_DEPTH",
            coerce=int,
        ),
        "strategy.update": ConfigItem("The default strategy for updating packages", "reuse", False),
        "strategy.save": ConfigItem("Specify how to save versions when a package is added", "minimum", False),
        "strategy.resolve_max_rounds": ConfigItem(
            "Specify the max rounds of resolution process",
            10000,
            env_var="PDM_RESOLVE_MAX_ROUNDS",
            coerce=int,
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
            "`symlink` or `pth` to create links to the cached installation",
            "symlink",
        ),
        "python.path": ConfigItem("The Python interpreter path", env_var="PDM_PYTHON"),
        "python.use_pyenv": ConfigItem("Use the pyenv interpreter", True, coerce=ensure_boolean),
        "python.use_venv": ConfigItem(
            "Install packages into the activated venv site packages instead of PEP 582",
            True,
            env_var="PDM_USE_VENV",
            coerce=ensure_boolean,
        ),
        "pypi.url": ConfigItem(
            "The URL of PyPI mirror, defaults to https://pypi.org/simple",
            DEFAULT_PYPI_INDEX,
            env_var="PDM_PYPI_URL",
        ),
        "pypi.verify_ssl": ConfigItem("Verify SSL certificate when query PyPI", True, coerce=ensure_boolean),
        "pypi.username": ConfigItem("The username to access PyPI", env_var="PDM_PYPI_USERNAME"),
        "pypi.password": ConfigItem("The password to access PyPI", env_var="PDM_PYPI_PASSWORD"),
        "pypi.ca_certs": ConfigItem(
            "Path to a CA certificate bundle used for verifying the identity of the PyPI server",
        ),
        "pypi.ignore_stored_index": ConfigItem(
            "Ignore the configured indexes",
            False,
            env_var="PDM_IGNORE_STORED_INDEX",
            coerce=ensure_boolean,
        ),
        "pypi.client_cert": ConfigItem(
            "Path to client certificate file, or combined cert/key file",
        ),
        "pypi.client_key": ConfigItem(
            "Path to client cert keyfile, if not in pypi.client_cert",
        ),
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
        defaults.update(cls.site)
        return defaults

    @classmethod
    def add_config(cls, name: str, item: ConfigItem) -> None:
        """Add or modify a config item"""
        cls._config_map[name] = item

    def __init__(self, config_file: Path, is_global: bool = False):
        self.is_global = is_global
        self.config_file = config_file.resolve()
        self.deprecated = {v.replace: k for k, v in self._config_map.items() if v.replace}
        self._file_data = load_config(self.config_file)
        self._data = collections.ChainMap(self._file_data, self.get_defaults() if is_global else {})

    def load_theme(self) -> rich.theme.Theme:
        if not self.is_global:  # pragma: no cover
            raise PdmUsageError("Theme can only be loaded from global config")
        return rich.theme.Theme({k[6:]: v for k, v in self.items() if k.startswith("theme.")})

    @property
    def self_data(self) -> dict[str, Any]:
        return dict(self._file_data)

    def iter_sources(self) -> Iterator[tuple[str, Source]]:
        for name, data in self._data.items():
            if name.startswith("pypi.") and name not in self._config_map:
                yield name[5:], cast(Source, dict(data, name=name))

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
        if parts[0] == REPOSITORY:
            if len(parts) < 2:
                raise PdmUsageError("Must specify a repository name")
            repo = self.get_repository_config(parts[1])
            if repo is None:
                raise KeyError(f"No repository named {parts[1]}")

            value = getattr(repo, parts[2]) if len(parts) >= 3 else repo
            if len(parts) >= 3 and parts[2] == "password" and value:
                return "<hidden>"
            return value
        elif parts[0] == "pypi" and key not in self._config_map:
            index_key = ".".join(parts[:2])
            if index_key not in self._data:
                raise KeyError(f"No PyPI index named {parts[1]}")
            source = self._data[index_key]
            if len(parts) >= 3 and parts[2] == "password":
                return "<hidden>"
            return source[parts[2]] if len(parts) >= 3 else RegistryConfig(**self._data[index_key])
        elif key == "pypi.password":
            return "<hidden>"

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
        parts = key.split(".")
        if parts[0] == REPOSITORY:
            if len(parts) < 3:
                raise PdmUsageError("Set repository config with [success]repository.{name}.{attr}")
            self._file_data.setdefault(parts[0], {}).setdefault(parts[1], {}).setdefault(parts[2], value)
            self._save_config()
            return
        if parts[0] == "pypi" and key not in self._config_map:
            if len(parts) < 3:
                raise PdmUsageError("Set index config with [success]pypi.{name}.{attr}")
            index_key = ".".join(parts[:2])
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
        env_var = config.env_var
        if env_var is not None and env_var in os.environ:
            ui.echo(
                "WARNING: the config is shadowed by env var '{}', the value set won't take effect.".format(env_var),
                style="warning",
            )
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
                keys.add(self.deprecated[key])
            elif key != REPOSITORY:
                keys.add(key)
        return iter(keys)

    def __delitem__(self, key: str) -> None:
        parts = key.split(".")
        if parts[0] == REPOSITORY:
            if len(parts) < 2:
                raise PdmUsageError("Should specify the name of repository")
            if len(parts) >= 3:
                del self._file_data.get(REPOSITORY, {}).get(parts[1], {})[parts[2]]
            else:
                del self._file_data.get(REPOSITORY, {})[parts[1]]
            self._save_config()
            return
        if parts[0] == "pypi" and key not in self._config_map:
            if len(parts) < 2:
                raise PdmUsageError("Should specify the name of index")
            if len(parts) >= 3:
                index_key, attr = key.rsplit(".", 1)
                del self._file_data.get(index_key, {})[attr]
            else:
                del self._file_data[key]
            self._save_config()
            return
        config_key = self.deprecated.get(key, key)
        config = self._config_map[config_key]
        self._file_data.pop(config_key, None)
        if config.replace:
            self._file_data.pop(config.replace, None)

        env_var = config.env_var
        if env_var is not None and env_var in os.environ:
            ui.echo(
                "WARNING: the config is shadowed by env var '{}', set value won't take effect.".format(env_var),
                style="warning",
            )
        self._save_config()

    def get_repository_config(self, name_or_url: str) -> RepositoryConfig | None:
        """Get a repository by name or url."""
        if not self.is_global:  # pragma: no cover
            raise NoConfigError("repository")
        repositories: Mapping[str, Source] = self._data.get(REPOSITORY, {})
        repo: RepositoryConfig | None = None
        if "://" in name_or_url:
            config: Source = next((v for v in repositories.values() if v.get("url") == name_or_url), {})
            repo = next(
                (r for r in DEFAULT_REPOSITORIES.values() if r.url == name_or_url),
                RepositoryConfig(name_or_url),
            )
        else:
            config = repositories.get(name_or_url, {})
            if name_or_url in DEFAULT_REPOSITORIES:
                repo = DEFAULT_REPOSITORIES[name_or_url]
        if repo:
            return dataclasses.replace(repo, **config)
        if not config:
            return None
        return RepositoryConfig(**config)  # type: ignore[misc]
