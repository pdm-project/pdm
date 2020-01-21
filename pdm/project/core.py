from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Union

import tomlkit
from pip._vendor.pkg_resources import safe_name
from vistir.contextmanagers import atomic_open_for_write

from pdm._types import Source
from pdm.context import context
from pdm.exceptions import ProjectError
from pdm.models.candidates import Candidate, identify
from pdm.models.environment import Environment
from pdm.models.repositories import BaseRepository, PyPIRepository
from pdm.models.requirements import Requirement, strip_extras, parse_requirement
from pdm.models.specifiers import PySpecSet
from pdm.project.config import Config
from pdm.project.meta import PackageMeta
from pdm.utils import find_project_root

if TYPE_CHECKING:
    from tomlkit.container import Container


def pyproject_cache(func):
    """Caches the function's result as long as the project file isn't changed."""
    _cache = _missing = object()

    def getter(self, *args, **kwargs):
        nonlocal _cache
        if self._pyproject is None or _cache is _missing:
            _cache = func(self, *args, **kwargs)
        return _cache

    return getter


def lockfile_cache(func):
    """Caches the function's result as long as the project file isn't changed."""
    _cache = _missing = object()

    def getter(self, *args, **kwargs):
        nonlocal _cache
        if self._lockfile is None or _cache is _missing:
            _cache = func(self, *args, **kwargs)
        return _cache

    return getter


class Project:
    PYPROJECT_FILENAME = "pyproject.toml"
    PDM_NAMESPACE = "tool.pdm"
    DEPENDENCIES_RE = re.compile(r"(?:(.+?)-)?dependencies")
    PYPROJECT_VERSION = "0.0.1"

    repository_class = PyPIRepository

    def __init__(self, root_path: Optional[str] = None) -> None:
        if root_path is None:
            root_path = find_project_root() or ""
        self.root = Path(root_path).absolute()
        self.pyproject_file = self.root / self.PYPROJECT_FILENAME
        self.lockfile_file = self.root / "pdm.lock"

        self._pyproject = None  # type: Optional[Container]
        self._lockfile = None  # type: Optional[Container]
        self._config = None  # type: Optional[Config]
        context.init(self)

    def __repr__(self) -> str:
        return f"<Project '{self.root.as_posix()}'>"

    @property
    def pyproject(self):
        # type: () -> Container
        if not self._pyproject:
            data = tomlkit.parse(self.pyproject_file.read_text("utf-8"))
            self._pyproject = data
        return self._pyproject

    @property
    @pyproject_cache
    def tool_settings(self):
        # type: () -> Union[Container, Dict]
        data = self.pyproject
        for sec in self.PDM_NAMESPACE.split("."):
            data = data.setdefault(sec, {})
        return data

    @property
    def lockfile(self):
        # type: () -> Container
        if not self.lockfile_file.is_file():
            raise ProjectError("Lock file does not exist.")
        if not self._lockfile:
            data = tomlkit.parse(self.lockfile_file.read_text("utf-8"))
            self._lockfile = data
        return self._lockfile

    @property
    def config(self) -> Config:
        if not self._config:
            self._config = Config(self.root)
        return self._config

    @property
    @pyproject_cache
    def is_pdm(self) -> bool:
        if not self.pyproject_file.is_file():
            return False
        return bool(self.tool_settings)

    @property
    @pyproject_cache
    def environment(self) -> Environment:
        return Environment(self.python_requires, self.config)

    @property
    @pyproject_cache
    def python_requires(self) -> PySpecSet:
        return PySpecSet(self.tool_settings.get("python_requires", ""))

    def get_dependencies(self, section: Optional[str] = None) -> Dict[str, Requirement]:
        if section in (None, "default"):
            deps = self.tool_settings.get("dependencies", [])
        elif section == "dev":
            deps = self.tool_settings.get("dev-dependencies", [])
        else:
            deps = self.tool_settings[f"{section}-dependencies"]
        result = {}
        for name, dep in deps.items():
            req = Requirement.from_req_dict(name, dep)
            req.from_section = section or "default"
            result[identify(req)] = req
        return result

    @property
    @pyproject_cache
    def dependencies(self) -> Dict[str, Requirement]:
        return self.get_dependencies()

    @property
    @pyproject_cache
    def dev_dependencies(self) -> Dict[str, Requirement]:
        return self.get_dependencies("dev")

    def iter_sections(self) -> Iterable[str]:
        for key in self.tool_settings:
            match = self.DEPENDENCIES_RE.match(key)
            if not match:
                continue
            section = match.group(1) or "default"
            yield section

    @property
    @pyproject_cache
    def all_dependencies(self) -> Dict[str, Dict[str, Requirement]]:
        return {
            section: self.get_dependencies(section) for section in self.iter_sections()
        }

    @property
    @pyproject_cache
    def allow_prereleases(self) -> Optional[bool]:
        return self.tool_settings.get("allow_prereleases")

    @property
    @pyproject_cache
    def sources(self) -> Optional[List[Source]]:
        return self.tool_settings.get("source")

    def get_repository(self) -> BaseRepository:
        sources = self.sources or []
        return self.repository_class(sources, self.environment)

    def get_project_metadata(self) -> Dict[str, Any]:
        content_hash = self.get_content_hash("md5")
        data = {
            "meta_version": self.PYPROJECT_VERSION,
            "content_hash": f"md5:{content_hash}",
        }
        if self.sources:
            data.update({"source": self.sources})
        return data

    def write_lockfile(self, toml_data: Container, show_message: bool = True) -> None:
        toml_data.update({"root": self.get_project_metadata()})

        with atomic_open_for_write(self.lockfile_file) as fp:
            fp.write(tomlkit.dumps(toml_data))
        if show_message:
            context.io.echo("Changes are written to pdm.lock.")
        self._lockfile = None

    def make_self_candidate(self, editable: bool = True) -> Candidate:
        req = parse_requirement(".", editable)
        req.name = self.meta.name
        return Candidate(
            req, self.environment, name=self.meta.name, version=self.meta.version
        )

    def get_locked_candidates(
        self, section: Optional[str] = None
    ) -> Dict[str, Candidate]:
        if not self.lockfile_file.is_file():
            return {}
        section = section or "default"
        result = {}
        for package in [dict(p) for p in self.lockfile["package"]]:
            if section != "__all__" and section not in package["sections"]:
                continue
            version = package.get("version")
            if version:
                package["version"] = f"=={version}"
            package_name = package.pop("name")
            req = Requirement.from_req_dict(package_name, dict(package))
            can = Candidate(req, self.environment, name=package_name, version=version)
            can.marker = req.marker
            can.hashes = {
                item["file"]: item["hash"]
                for item in self.lockfile["metadata"].get(
                    f"{package_name} {version}", []
                )
            } or None
            result[identify(req)] = can
        if section == "default" and self.meta.name:
            result[safe_name(self.meta.name).lower()] = self.make_self_candidate()
        return result

    def get_content_hash(self, algo: str = "md5") -> str:
        pyproject_content = tomlkit.dumps(self.tool_settings)
        hasher = hashlib.new(algo)
        hasher.update(pyproject_content.encode("utf-8"))
        return hasher.hexdigest()

    def is_lockfile_hash_match(self) -> bool:
        if not self.lockfile_file.exists():
            return False
        hash_in_lockfile = str(self.lockfile["root"]["content_hash"])
        algo, hash_value = hash_in_lockfile.split(":")
        content_hash = self.get_content_hash(algo)
        return content_hash == hash_value

    def add_dependencies(
        self, requirements: Dict[str, Requirement], show_message: bool = True
    ) -> None:
        for name, dep in requirements.items():
            if dep.from_section == "default":
                deps = self.tool_settings["dependencies"]
            elif dep.from_section == "dev":
                deps = self.tool_settings["dev-dependencies"]
            else:
                section = f"{dep.from_section}-dependencies"
                if section not in self.tool_settings:
                    self.tool_settings[section] = tomlkit.table()
                deps = self.tool_settings[section]

            matched_name = next(
                filter(
                    lambda k: strip_extras(name)[0] == safe_name(k).lower(), deps.keys()
                ),
                None,
            )
            name_to_save = dep.name if matched_name is None else matched_name
            _, req_dict = dep.as_req_dict()
            if isinstance(req_dict, dict):
                req = tomlkit.inline_table()
                req.update(req_dict)
                req_dict = req
            deps[name_to_save] = req_dict
        self.write_pyproject(show_message)

    def write_pyproject(self, show_message: bool = True) -> None:
        with atomic_open_for_write(
            self.pyproject_file.as_posix(), encoding="utf-8"
        ) as f:
            f.write(tomlkit.dumps(self.pyproject))
        if show_message:
            context.io.echo("Changes are written to pyproject.toml.")
        self._pyproject = None

    def init_pyproject(self) -> None:
        if not self._pyproject:
            self._pyproject = {}
        self._pyproject.update(
            {
                "tool": {
                    "pdm": {
                        "dependencies": tomlkit.table(),
                        "dev-dependencies": tomlkit.table(),
                    }
                }
            }
        )
        self.write_pyproject()

    @property
    @pyproject_cache
    def meta(self) -> PackageMeta:
        return PackageMeta(self)
