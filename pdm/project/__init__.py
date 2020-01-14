import hashlib
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import tomlkit
from pdm.context import context
from pdm.models.candidates import Candidate
from pdm.models.repositories import BaseRepository, PyPIRepository
from pdm.models.requirements import Requirement
from pdm.models.specifiers import PySpecSet
from pdm.project.config import Config
from pdm.types import Source
from pdm.utils import find_project_root
from vistir.contextmanagers import atomic_open_for_write

if TYPE_CHECKING:
    from tomlkit.toml_document import TOMLDocument


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
            root_path = find_project_root()
        self.root = Path(root_path)
        self.pyproject_file = self.root / self.PYPROJECT_FILENAME
        self.lockfile_file = self.root / "pdm.lock"
        self.packages_root = None

        self._pyproject = None  # type: Optional[TOMLDocument]
        self._lockfile = None  # type: Optional[TOMLDocument]
        self._config = None  # type: Optional[Config]
        context.init(self)

    def __repr__(self) -> str:
        return f"<Project '{self.root.as_posix()}'>"

    @property
    def pyproject(self):
        # type: () -> TOMLDocument
        if not self._pyproject:
            data = tomlkit.parse(self.pyproject_file.read_text("utf-8"))
            for sec in self.PDM_NAMESPACE.split("."):
                data = data[sec]
            self._pyproject = data
        return self._pyproject

    @property
    def lockfile(self):
        # type: () -> TOMLDocument
        if not self._lockfile and self.lockfile_file.exists():
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
    def python_requires(self) -> PySpecSet:
        return PySpecSet(self.pyproject.get("python_requires", ""))

    def get_dependencies(self, section: Optional[str] = None) -> List[Requirement]:
        if section is None:
            deps = self.pyproject.get("dependencies", [])
        elif section == "dev":
            deps = self.pyproject.get("dev-dependencies", [])
        else:
            deps = self.pyproject[f"{section}-dependencies"]
        result = []
        for name, dep in deps.items():
            req = Requirement.from_req_dict(name, dep)
            req.from_section = section or "default"
            result.append(req)
        return result

    @property
    @pyproject_cache
    def dependencies(self) -> List[Requirement]:
        return self.get_dependencies()

    @property
    @pyproject_cache
    def dev_dependencies(self) -> List[Requirement]:
        return self.get_dependencies("dev")

    @property
    @pyproject_cache
    def all_dependencies(self) -> List[Requirement]:
        result = []
        for key in self.pyproject:
            match = self.DEPENDENCIES_RE.match(key)
            if not match:
                continue
            section = match.group(1) or None
            result.extend(self.get_dependencies(section))
        return result

    @property
    @pyproject_cache
    def allow_prereleases(self) -> Optional[bool]:
        return self.pyproject.get("allow_prereleases")

    @property
    @pyproject_cache
    def sources(self) -> Optional[List[Source]]:
        return self.pyproject.get("source")

    def get_repository(self) -> BaseRepository:
        sources = self.sources or []
        return self.repository_class(sources)

    def get_project_metadata(self) -> Dict[str, Any]:
        pyproject_content = tomlkit.dumps(self.pyproject)
        content_hash = (
            "md5:" + hashlib.md5(pyproject_content.encode("utf-8")).hexdigest()
        )
        data = {"meta_version": self.PYPROJECT_VERSION, "content_hash": content_hash}
        if self.sources:
            data.update({"source": self.sources})
        return data

    def write_lockfile(self, toml_data: tomlkit.toml_document.TOMLDocument) -> None:
        toml_data.update({"root": self.get_project_metadata()})

        with atomic_open_for_write(self.lockfile_file) as fp:
            fp.write(tomlkit.dumps(toml_data))
        self._lockfile = None

    def get_locked_candidates(self, section: Optional[str] = None) -> List[Candidate]:
        repository = self.get_repository()
        section = section or "default"
        result = []
        for package in self.lockfile["package"]:
            if section not in package["sections"]:
                continue
            version = package.get("version")
            if version:
                package["version"] = f"=={version}"
            req = Requirement.from_req_dict(package["name"], dict(package))
            can = Candidate(req, repository, name=package["name"], version=version)
            can.hashes = {
                item["file"]: item["hash"]
                for item in self.lockfile["metadata"].get(
                    f"{package['name']} {version}", []
                )
            }
            result.append(can)
        return result

    def is_lockfile_hash_match(self) -> bool:
        if not self.lockfile_file.exists():
            return False
        hash_in_lockfile = self.lockfile["root"]["content_hash"]
        algo, hash_value = hash_in_lockfile.split(":")
        hasher = hashlib.new(algo)
        pyproject_content = tomlkit.dumps(self.pyproject)
        content_hash = hasher(pyproject_content.encode("utf-8")).hexdigest()
        return content_hash == hash_value
