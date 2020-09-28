import re
from pathlib import Path

import tomlkit
import tomlkit.exceptions

from pdm.formats.base import MetaConverter, convert_from
from pdm.models.requirements import parse_requirement


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
    email = f" <{email}>" if email else ""
    return f"{name}{email}"


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
            self._data["author"] = _get_author(metadata)
        if "maintainer" in metadata:
            self._data["maintainer"] = _get_author(metadata, "maintainer")
        if "urls" in metadata:
            self._data["project_urls"] = metadata.pop("urls")
        if "home-page" in metadata:
            self._data["homepage"] = metadata.pop("home-page")
        if "description-file" in metadata:
            self._data["readme"] = metadata.pop("description-file")
        if "requires-python" in metadata:
            self._data["python_requires"] = metadata.pop("requires-python")
        # requirements
        self._data["dependencies"] = dict(
            parse_requirement(line).as_req_dict()
            for line in metadata.pop("requires", [])
        )
        extra_reqs = metadata.pop("requires-extra", {})
        extras = []
        for key, reqs in extra_reqs.items():
            extras.append(key)
            self._data[f"{key}-dependencies"] = dict(
                parse_requirement(line).as_req_dict() for line in reqs
            )
        if extras:
            self._data["extras"] = extras
        # Add remaining metadata as the same key
        self._data.update(metadata)
        return self._data["name"]

    @convert_from("scripts")
    def cli(self, value):
        return value

    @convert_from("entrypoints")
    def entry_points(self, value):
        return value

    @convert_from("sdist")
    def includes(self, value):
        self._data["excludes"] = value.get("exclude")
        return value.get("include")


def convert(project, filename):
    with open(filename, encoding="utf-8") as fp:
        return dict(
            FlitMetaConverter(tomlkit.parse(fp.read())["tool"]["flit"], filename)
        )


def export(project, candidates, options):
    raise NotImplementedError()
