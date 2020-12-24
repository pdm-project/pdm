import re
from pathlib import Path

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


class FlitMetaConverter(MetaConverter):
    VERSION_RE = re.compile(r"__version__\s*=\s*['\"](.+?)['\"]")

    @convert_from("metadata")
    def name(self, metadata):
        # name
        module = metadata.pop("module")
        self._data["name"] = metadata.pop("dist-name", module)
        # version
        parent_dir = Path(self.filename).parent
        if (parent_dir / module / "__init__.py").exists():
            source = parent_dir / module / "__init__.py"
        else:
            source = parent_dir / f"{module}.py"
        self._data["version"] = self.VERSION_RE.findall(
            source.read_text(encoding="utf-8")
        )[0]
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


def convert(project, filename):
    with open(filename, encoding="utf-8") as fp:
        return (
            dict(FlitMetaConverter(tomlkit.parse(fp.read())["tool"]["flit"], filename)),
            {},
        )


def export(project, candidates, options):
    raise NotImplementedError()
