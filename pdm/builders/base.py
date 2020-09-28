from __future__ import annotations

import atexit
import glob
import os
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Iterator, List

from pip._vendor.pkg_resources import normalize_path

from pdm.exceptions import ProjectError
from pdm.project import Project

if TYPE_CHECKING:
    from pip_shims import shims

OPEN_README = """import codecs

with codecs.open({readme!r}, encoding="utf-8") as fp:
    long_description = fp.read()
"""

SETUP_FORMAT = """
# -*- coding: utf-8 -*-
from setuptools import setup

{before}
setup_kwargs = {{
    'name': {name!r},
    'version': {version!r},
    'description': {description!r},
    'long_description': long_description,
    'license': {license!r},
    'author': {author!r},
    'author_email': {author_email!r},
    'maintainer': {maintainer!r},
    'maintainer_email': {maintainer_email!r},
    'url': {url!r},
{extra}
}}
{after}

setup(**setup_kwargs)
"""

METADATA_BASE = """\
Metadata-Version: 2.1
Name: {name}
Version: {version}
Summary: {description}
Home-page: {homepage}
License: {license}
"""


def _match_path(path, pattern):
    return normalize_path(path) == normalize_path(pattern)


def _merge_globs(include_globs, excludes_globs):
    includes, excludes = [], []
    for path, key in include_globs.items():
        # The longer glob pattern wins
        if path in excludes_globs:
            if len(key) <= excludes_globs[path]:
                continue
            else:
                del excludes_globs[path]
        includes.append(path)
    excludes = list(excludes_globs)
    return includes, excludes


def _find_top_packages(root) -> List[str]:
    result = []
    for path in os.listdir(root):
        if (
            os.path.isdir(path)
            and os.path.exists(os.path.join(path, "__init__.py"))
            and not path.startswith("test")
        ):
            result.append(path)
    return result


def _format_list(data: List[str], indent=4) -> str:
    result = ["["]
    for row in data:
        result.append(" " * indent + repr(row) + ",")
    result.append(" " * (indent - 4) + "]")
    return "\n".join(result)


def _format_dict_list(data: Dict[str, List[str]], indent=4) -> str:
    result = ["{"]
    for key, value in data.items():
        result.append(
            " " * indent + repr(key) + ": " + _format_list(value, indent + 4) + ","
        )
    result.append(" " * (indent - 4) + "}")
    return "\n".join(result)


class Builder:
    """Base class for building and distributing a package from given path."""

    DEFAULT_EXCLUDES = ["ez_setup", "*__pycache__", "tests", "tests.*"]

    def __init__(self, ireq: shims.InstallRequirement) -> None:
        self.ireq = ireq
        self.project = Project(ireq.unpacked_source_directory)
        self._old_cwd = None
        self.package_dir = None

    def __enter__(self) -> "Builder":
        self._old_cwd = os.getcwd()
        os.chdir(self.ireq.unpacked_source_directory)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        os.chdir(self._old_cwd)

    @property
    def meta(self):
        return self.project.meta

    def build(self, build_dir: str, **kwargs) -> str:
        raise NotImplementedError

    def _find_files_iter(self, include_build: bool = False) -> Iterator[str]:
        includes = []
        find_froms = []
        excludes = []
        dont_find_froms = []

        if not self.meta.includes:
            if os.path.isdir("src"):
                find_froms = ["src"]
                self.package_dir = "src"
            else:
                find_froms = _find_top_packages(".")
            if not find_froms:
                includes = ["*.py"]
        else:
            for pat in self.meta.includes:
                if os.path.basename(pat) == "*":
                    pat = pat[:-2]
                if "*" in pat or os.path.isfile(pat):
                    includes.append(pat)
                else:
                    find_froms.append(pat)

        if self.meta.excludes:
            for pat in self.meta.excludes:
                if "*" in pat or os.path.isfile(pat):
                    excludes.append(pat)
                else:
                    dont_find_froms.append(pat)

        include_globs = {path: key for key in includes for path in glob.glob(key)}
        excludes_globs = {path: key for key in excludes for path in glob.glob(key)}

        includes, excludes = _merge_globs(include_globs, excludes_globs)

        for path in find_froms:
            path_base = os.path.dirname(path)
            if not path_base or path_base == ".":
                # the path is top level itself
                path_base = path
            if (
                not os.path.isfile(os.path.join(path_base, "__init__.py"))
                and _find_top_packages(path_base)
                and not self.package_dir
            ):  # Determine package_dir smartly
                self.package_dir = path_base

            for root, dirs, filenames in os.walk(path):
                if root == "__pycache__" or any(
                    _match_path(root, item) for item in dont_find_froms
                ):
                    continue

                for filename in filenames:
                    if filename.endswith(".pyc") or any(
                        _match_path(os.path.join(root, filename), item)
                        for item in excludes
                    ):
                        continue
                    yield os.path.join(root, filename)

        for path in includes:
            if os.path.isfile(path):
                yield path
        if not include_build:
            return

        if self.meta.build and os.path.isfile(self.meta.build):
            yield self.meta.build

        for pat in ("COPYING", "LICENSE"):
            for path in glob.glob(pat + "*"):
                if os.path.isfile(path):
                    yield path

        if self.meta.readme and os.path.isfile(self.meta.readme):
            yield self.meta.readme

        if self.project.pyproject_file.exists():
            yield "pyproject.toml"

    def find_files_to_add(self, include_build: bool = False) -> List[Path]:
        """Traverse the project path and return a list of file names
        that should be included in a sdist distribution.
        If include_build is True, will include files like LICENSE, README and pyproject
        Produce a paths list relative to the source dir.
        """
        return sorted(set(Path(p) for p in self._find_files_iter(include_build)))

    def format_setup_py(self) -> str:
        before, extra, after = [], [], []
        meta = self.meta
        kwargs = {
            "name": meta.name,
            "version": meta.version,
            "author": meta.author,
            "license": meta.license,
            "author_email": meta.author_email,
            "maintainer": meta.maintainer,
            "maintainer_email": meta.maintainer_email,
            "description": meta.description,
            "url": meta.homepage,
        }

        if meta.build:
            # The build script must contain a `build(setup_kwargs)`, we just import
            # and execute it.
            after.extend(
                [
                    "from {} import build\n".format(meta.build.split(".")[0]),
                    "build(setup_kwargs)\n",
                ]
            )

        package_paths = meta.convert_package_paths()
        if package_paths["packages"]:
            extra.append("    'packages': {!r},\n".format(package_paths["packages"]))
        if package_paths["package_dir"]:
            extra.append(
                "    'package_dir': {!r},\n".format(package_paths["package_dir"])
            )
        if package_paths["package_data"]:
            extra.append(
                "    'package_data': {!r},\n".format(package_paths["package_data"])
            )
        if package_paths["exclude_package_data"]:
            extra.append(
                "    'exclude_package_data': {!r},\n".format(
                    package_paths["exclude_package_data"]
                )
            )

        if meta.readme:
            before.append(OPEN_README.format(readme=meta.readme))
        else:
            before.append("long_description = None\n")
        if meta.long_description_content_type:
            extra.append(
                "    'long_description_content_type': {!r},\n".format(
                    meta.long_description_content_type
                )
            )

        if meta.keywords:
            extra.append("    'keywords': {!r},\n".format(meta.keywords))
        if meta.classifiers:
            extra.append(
                "    'classifiers': {},\n".format(_format_list(meta.classifiers, 8))
            )
        if meta.install_requires:
            before.append(
                "INSTALL_REQUIRES = {}\n".format(_format_list(meta.install_requires))
            )
            extra.append("    'install_requires': INSTALL_REQUIRES,\n")
        if meta.extras_require:
            before.append(
                "EXTRAS_REQUIRE = {}\n".format(_format_dict_list(meta.extras_require))
            )
            extra.append("    'extras_require': EXTRAS_REQUIRE,\n")
        if meta.python_requires:
            extra.append("    'python_requires': {!r},\n".format(meta.python_requires))
        if meta.entry_points:
            before.append(
                "ENTRY_POINTS = {}\n".format(_format_dict_list(meta.entry_points))
            )
            extra.append("    'entry_points': ENTRY_POINTS,\n")
        return SETUP_FORMAT.format(
            before="".join(before), after="".join(after), extra="".join(extra), **kwargs
        )

    def format_pkginfo(self, full=True) -> str:
        meta = self.meta
        content = METADATA_BASE.format(
            name=meta.name or "UNKNOWN",
            version=meta.version or "UNKNOWN",
            homepage=meta.homepage or "UNKNOWN",
            license=meta.license or "UNKNOWN",
            description=meta.description or "UNKNOWN",
            readme=(Path(meta.readme).read_text("utf-8") if meta.readme else "UNKNOWN"),
        )

        # Optional fields
        if meta.keywords:
            content += "Keywords: {}\n".format(",".join(meta.keywords))

        if meta.author:
            content += "Author: {}\n".format(meta.author)

        if meta.author_email:
            content += "Author-email: {}\n".format(meta.author_email)

        if meta.maintainer:
            content += "Maintainer: {}\n".format(meta.maintainer)

        if meta.maintainer_email:
            content += "Maintainer-email: {}\n".format(meta.maintainer_email)

        if meta.python_requires:
            content += "Requires-Python: {}\n".format(meta.python_requires)

        for classifier in meta.classifiers or []:
            content += "Classifier: {}\n".format(classifier)

        if full:
            for dep in sorted(meta.install_requires):
                content += "Requires-Dist: {}\n".format(dep)

        for extra, reqs in sorted(self.meta.requires_extra.items()):
            content += "Provides-Extra: {}\n".format(extra)
            if full:
                for dep in reqs:
                    content += "Requires-Dist: {}\n".format(dep)

        for url in sorted(meta.project_urls or {}):
            content += "Project-URL: {}, {}\n".format(url, meta.project_urls[url])

        if meta.long_description_content_type:
            content += "Description-Content-Type: {}\n".format(
                meta.long_description_content_type
            )
        if meta.readme:
            readme = Path(meta.readme).read_text("utf-8")
            if full:
                content += "\n" + readme + "\n"
            else:
                content += "Description: {}\n".format(
                    textwrap.indent(readme, " " * 8).lstrip()
                )

        return content

    def ensure_setup_py(self, clean: bool = True) -> None:
        """Ensures the requirement has a setup.py ready."""
        # XXX: Currently only handle PDM project, and do nothing if not.

        if not self.ireq.source_dir or os.path.isfile(self.ireq.setup_py_path):
            return

        setup_py_path = self.ireq.setup_py_path
        if not self.project.is_pdm:
            raise ProjectError(
                "General PEP 517 editable build is not supported "
                "except for PDM proects."
            )
        setup_py_content = self.format_setup_py()

        with open(setup_py_path, "w", encoding="utf-8") as fp:
            fp.write(setup_py_content)

        # Clean this temp file when process exits
        def cleanup():
            os.unlink(setup_py_path)

        if clean:
            atexit.register(cleanup)
