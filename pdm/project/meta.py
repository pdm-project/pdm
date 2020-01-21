from __future__ import annotations

import glob
import os
import re
from typing import TYPE_CHECKING, List, Dict, Union

import setuptools
import vistir
from pkg_resources import safe_name

from pdm.exceptions import ProjectError

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

    name = MetaField("name")
    version = MetaField("version")
    homepage = MetaField("homepage")
    license = MetaField("license")

    def _get_name(self, value):
        return _NAME_EMAIL_RE.match(value).group(1)

    def _get_email(self, value):
        return _NAME_EMAIL_RE.match(value).group(2)

    author = MetaField("author", _get_name)
    author_email = MetaField("author", _get_email)
    maintainer = MetaField("maintainer", _get_name)
    maintainer_email = MetaField("maintainer", _get_email)
    classifiers = MetaField("classifiers")
    description = MetaField("description")
    keywords = MetaField("keywords")
    project_urls = MetaField("project_urls")
    includes = MetaField("includes")
    excludes = MetaField("excludes")
    build = MetaField("build")

    @property
    def project_name(self) -> str:
        return safe_name(self.name)

    def _determine_content_type(self, value):
        if value.endswith(".md"):
            return "text/markdown"
        return None

    readme = MetaField("readme")
    long_description_content_type = MetaField("readme", _determine_content_type)
    _extras = MetaField("extras")

    @property
    def install_requires(self) -> List[str]:
        return [r.as_line() for r in self.project.get_dependencies().values()]

    @property
    def extras_require(self) -> Dict[str, List[str]]:
        if not self._extras:
            return {}
        return {
            extra: [r.as_line() for r in self.project.get_dependencies(extra).values()]
            for extra in self._extras
        }

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
        if "plugins" in settings:
            for plugin, value in settings["plugins"].items():
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

        with vistir.cd(self.project.root.as_posix()):
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
                        temp = setuptools.find_packages(include)
                        if os.path.exists(include + "/__init__.py"):
                            temp.append(include)
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
