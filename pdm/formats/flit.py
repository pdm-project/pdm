import ast
import re
from pathlib import Path
from typing import Optional, Tuple

import tomlkit
import tomlkit.exceptions

from pdm.formats.base import (
    MetaConverter,
    array_of_inline_tables,
    convert_from,
    make_array,
    make_inline_table,
)


def check_fingerprint(project, filename):
    with open(filename, encoding="utf-8") as fp:
        try:
            data = tomlkit.parse(fp.read())
        except tomlkit.exceptions.TOMLKitError:
            return False

    return "tool" in data and "flit" in data["tool"]


def _get_author(metadata, type_="author"):
    name = metadata.pop(type_)
    email = metadata.pop(f"{type_}-email", None)
    return array_of_inline_tables([{"name": name, "email": email}])


def get_docstring_and_version_via_ast(
    target: Path,
) -> Tuple[Optional[str], Optional[str]]:
    """
    This function is borrowed from flit's implementation, but does not attempt to import
    that file. If docstring or version can't be retrieved by this function,
    they are just left empty.
    """
    # read as bytes to enable custom encodings
    node = ast.parse(target.read_bytes())
    for child in node.body:
        # Only use the version from the given module if it's a simple
        # string assignment to __version__
        is_version_str = (
            isinstance(child, ast.Assign)
            and len(child.targets) == 1
            and isinstance(child.targets[0], ast.Name)
            and child.targets[0].id == "__version__"
            and isinstance(child.value, ast.Str)
        )
        if is_version_str:
            version = child.value.s
            break
    else:
        version = None
    return ast.get_docstring(node), version


class FlitMetaConverter(MetaConverter):
    VERSION_RE = re.compile(r"__version__\s*=\s*['\"](.+?)['\"]")

    @convert_from("metadata")
    def name(self, metadata):
        # name
        module = metadata.pop("module")
        self._data["name"] = metadata.pop("dist-name", module)
        # version and description
        parent_dir = Path(self.filename).parent
        if (parent_dir / module / "__init__.py").exists():
            source = parent_dir / module / "__init__.py"
        else:
            source = parent_dir / f"{module}.py"

        version = self._data.get("version")
        description = self._data.get("description")
        description_in_ast, version_in_ast = get_docstring_and_version_via_ast(source)
        self._data["version"] = version or version_in_ast
        self._data["description"] = description or description_in_ast
        # author and maintainer
        if "author" in metadata:
            self._data["authors"] = _get_author(metadata)
        if "maintainer" in metadata:
            self._data["maintainers"] = _get_author(metadata, "maintainer")
        if "license" in metadata:
            self._data["license"] = make_inline_table({"text", metadata.pop("license")})
            self._data["dynamic"] = ["classifiers"]
        if "urls" in metadata:
            self._data["urls"] = metadata.pop("urls")
        if "home-page" in metadata:
            self._data.setdefault("urls", {})["homepage"] = metadata.pop("home-page")
        if "description-file" in metadata:
            self._data["readme"] = metadata.pop("description-file")
        if "requires-python" in metadata:
            self._data["requires-python"] = metadata.pop("requires-python")
            self._data["dynamic"] = ["classifiers"]
        # requirements
        self._data["dependencies"] = make_array(metadata.pop("requires", []), True)
        self._data["optional-dependencies"] = metadata.pop("requires-extra", {})
        # Add remaining metadata as the same key
        self._data.update(metadata)
        return self._data["name"]

    @convert_from("entrypoints", name="entry-points")
    def entry_points(self, value):
        return value

    @convert_from("sdist")
    def includes(self, value):
        self._data["excludes"] = value.get("exclude")
        return value.get("include")


def convert(project, filename, options):
    with open(filename, encoding="utf-8") as fp:
        return (
            dict(FlitMetaConverter(tomlkit.parse(fp.read())["tool"]["flit"], filename)),
            {},
        )


def export(project, candidates, options):
    raise NotImplementedError()
