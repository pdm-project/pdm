from __future__ import annotations

import glob
import os
import re
from typing import TYPE_CHECKING, Dict, List, Union

import setuptools
from pkg_resources import safe_name

from pdm.exceptions import ProjectError
from pdm.models.markers import Marker
from pdm.utils import cd

if TYPE_CHECKING:
    from pdm.project import Project


class MetaField:
    def __init__(self, name, fget=None):
        self.name = name
        self.fget = fget

    def __get__(self, instance, owner):
        if not instance:
            return self
        try:
            rv = instance.project.tool_settings[self.name]
            if self.fget is not None:
                rv = self.fget(instance, rv)
            return rv
        except KeyError:
            return None


_NAME_EMAIL_RE = re.compile(r"^\s*([^<>]+?)\s*<([^<>]+)>")


class PackageMeta:
    """A class that holds all metadata that Python packaging requries."""

    def __init__(self, project: Project) -> None:
        self.project = project

    name: str = MetaField("name")

    def _get_version(self, value):
        if isinstance(value, str):
            return value
        version_source = value.get("from")
        with self.project.root.joinpath(version_source).open(encoding="utf-8") as fp:
            version = re.findall(
                r"^__version__\s*=\s*[\"'](.+?)[\"']\s*$", fp.read(), re.M
            )[0]
        return version

    version: str = MetaField("version", _get_version)
    homepage: str = MetaField("homepage")
    license: str = MetaField("license")

    def _get_name(self, value):
        m = _NAME_EMAIL_RE.match(value)
        return m.group(1) if m else None

    def _get_email(self, value):
        m = _NAME_EMAIL_RE.match(value)
        return m.group(2) if m else None

    author: str = MetaField("author", _get_name)
    author_email: str = MetaField("author", _get_email)
    maintainer: str = MetaField("maintainer", _get_name)
    maintainer_email: str = MetaField("maintainer", _get_email)
    classifiers: List[str] = MetaField("classifiers")
    description: str = MetaField("description")
    keywords: str = MetaField("keywords")
    project_urls: Dict[str, str] = MetaField("project_urls")
    includes: List[str] = MetaField("includes")
    excludes: List[str] = MetaField("excludes")
    build: str = MetaField("build")

    @property
    def project_name(self) -> str:
        return safe_name(self.name)

    def _determine_content_type(self, value):
        if value.endswith(".md"):
            return "text/markdown"
        return None

    readme: str = MetaField("readme")
    long_description_content_type: str = MetaField("readme", _determine_content_type)
    _extras: List[str] = MetaField("extras")

    @property
    def install_requires(self) -> List[str]:
        # Exclude editable requirements for not supported in `install_requires`
        # field.
        return [
            r.as_line()
            for r in self.project.get_dependencies().values()
            if not r.editable
        ]

    @property
    def extras_require(self) -> Dict[str, List[str]]:
        """For setup.py extras_require field"""
        if not self._extras:
            return {}
        return {
            extra: [r.as_line() for r in self.project.get_dependencies(extra).values()]
            for extra in self._extras
        }

    @property
    def requires_extra(self) -> Dict[str, List[str]]:
        """For PKG-INFO metadata"""
        if not self._extras:
            return {}
        result = {}
        for extra in self._extras:
            current = result[extra] = []
            for r in self.project.get_dependencies(extra).values():
                r.marker = Marker(f"extra == {extra!r}") & r.marker
                current.append(r.as_line())
        return result

    @property
    def python_requires(self) -> str:
        return str(self.project.python_requires)

    @property
    def entry_points(self) -> Dict[str, List[str]]:
        result = {}
        settings = self.project.tool_settings
        if "cli" in settings:
            result["console_scripts"] = [
                f"{key} = {value}" for key, value in settings["cli"].items()
            ]
        if "entry_points" in settings:
            for plugin, value in settings["entry_points"].items():
                result[plugin] = [f"{k} = {v}" for k, v in value.items()]
        return result

    def convert_package_paths(self) -> Dict[str, Union[List, Dict]]:
        """Return a {package_dir, packages, package_data, exclude_package_data} dict.
        """
        package_dir = {}
        packages = []
        py_modules = []
        package_data = {"": ["*"]}
        exclude_package_data = {}

        with cd(self.project.root.as_posix()):
            if not self.includes:
                if os.path.isdir("src"):
                    package_dir[""] = "src"
                    packages = setuptools.find_packages("src")
                else:
                    packages = setuptools.find_packages(exclude=["tests", "tests.*"])
                if not packages:
                    py_modules = [path[:-3] for path in glob.glob("*.py")]
            else:
                packages_set = set()
                includes = self.includes
                for include in includes[:]:
                    if include.replace("\\", "/").endswith("/*"):
                        include = include[:-2]
                    if "*" not in include and os.path.isdir(include):
                        include = include.rstrip("/\\")
                        temp = setuptools.find_packages(include)
                        if os.path.exists(include + "/__init__.py"):
                            temp = [include] + [f"{include}.{part}" for part in temp]
                        elif temp:
                            package_dir[""] = include
                        packages_set.update(temp)
                        includes.remove(include)
                packages[:] = list(packages_set)
                for include in includes:
                    for path in glob.glob(include):
                        if "/" not in path.lstrip("./") and path.endswith(".py"):
                            # Only include top level py modules
                            py_modules.append(path.lstrip("./")[:-3])
                    if include.endswith(".py"):
                        continue
                    for package in packages:
                        relpath = os.path.relpath(include, package)
                        if not relpath.startswith(".."):
                            package_data.setdefault(package, []).append(relpath)
                for exclude in self.excludes or []:
                    for package in packages:
                        relpath = os.path.relpath(exclude, package)
                        if not relpath.startswith(".."):
                            exclude_package_data.setdefault(package, []).append(relpath)
            if packages and py_modules:
                raise ProjectError(
                    "Can't specify packages and py_modules at the same time."
                )
        return {
            "package_dir": package_dir,
            "packages": packages,
            "py_modules": py_modules,
            "package_data": package_data,
            "exclude_package_data": exclude_package_data,
        }
