import functools
import operator
import os
import re

import toml

from pdm.formats.base import (
    MetaConverter,
    Unset,
    convert_from,
    make_array,
    make_inline_table,
    parse_name_email,
)
from pdm.models.markers import Marker
from pdm.models.requirements import Requirement
from pdm.models.specifiers import PySpecSet
from pdm.utils import cd


def check_fingerprint(project, filename):
    with open(filename, encoding="utf-8") as fp:
        try:
            data = toml.load(fp)
        except toml.TomlDecodeError:
            return False

    return "tool" in data and "poetry" in data["tool"]


VERSION_RE = re.compile(r"([^\d\s]*)\s*(\d.*?)\s*(?=,|$)")


def _convert_specifier(version):
    parts = []
    for op, version in VERSION_RE.findall(str(version)):
        if op == "~":
            op += "="
        elif op == "^":
            major, *vparts = version.split(".")
            next_major = ".".join([str(int(major) + 1)] + ["0"] * len(vparts))
            parts.append(f">={version},<{next_major}")
            continue
        elif not op:
            op = "=="
        parts.append(f"{op}{version}")
    return ",".join(parts)


def _convert_python(python):
    if not python:
        return PySpecSet()
    parts = [PySpecSet(_convert_specifier(s)) for s in python.split("||")]
    return functools.reduce(operator.or_, parts)


def _convert_req(name, req_dict):
    if not getattr(req_dict, "items", None):
        return Requirement.from_req_dict(name, _convert_specifier(req_dict)).as_line()
    req_dict = dict(req_dict)
    if "version" in req_dict:
        req_dict["version"] = _convert_specifier(req_dict["version"])
    markers = []
    if "markers" in req_dict:
        markers.append(Marker(req_dict.pop("markers")))
    if "python" in req_dict:
        markers.append(
            Marker(_convert_python(req_dict.pop("python")).as_marker_string())
        )
    if markers:
        req_dict["marker"] = str(functools.reduce(operator.and_, markers)).replace(
            '"', "'"
        )
    if "rev" in req_dict or "branch" in req_dict or "tag" in req_dict:
        req_dict["ref"] = req_dict.pop(
            "rev", req_dict.pop("tag", req_dict.pop("branch", None))
        )
    return Requirement.from_req_dict(name, req_dict).as_line()


class PoetryMetaConverter(MetaConverter):
    @convert_from("authors")
    def authors(self, value):
        return parse_name_email(value)

    @convert_from("maintainers")
    def maintainers(self, value):
        return parse_name_email(value)

    @convert_from("license")
    def license(self, value):
        self._data["dynamic"] = ["classifiers"]
        return make_inline_table({"text": value})

    @convert_from(name="requires-python")
    def requires_python(self, source):
        python = source.get("dependencies", {}).pop("python", None)
        self._data["dynamic"] = ["classifiers"]
        return str(_convert_python(python))

    @convert_from()
    def urls(self, source):
        rv = source.pop("urls", {})
        if "homepage" in source:
            rv["homepage"] = source.pop("homepage")
        if "repository" in source:
            rv["repository"] = source.pop("repository")
        if "documentation" in source:
            rv["documentation"] = source.pop("documentation")
        return rv

    @convert_from("plugins", name="entry-points")
    def entry_points(self, value):
        return value

    @convert_from()
    def dependencies(self, source):
        rv = []
        value, extras = dict(source["dependencies"]), source.pop("extras", {})
        for key, req_dict in value.items():
            optional = getattr(req_dict, "items", None) and req_dict.pop(
                "optional", False
            )
            req = _convert_req(key, req_dict)
            if optional:
                extra = next((k for k, v in extras.items() if key in v), None)
                if extra:
                    self._data.setdefault("optional-dependencies", {}).setdefault(
                        extra, []
                    ).append(req)
            else:
                rv.append(req)
        del source["dependencies"]
        return make_array(rv, True)

    @convert_from("dev-dependencies", name="dev-dependencies")
    def dev_dependencies(self, value):
        return make_array([_convert_req(key, req) for key, req in value.items()], True)

    @convert_from()
    def includes(self, source):
        result = []
        for item in source.pop("packages", []):
            include = item["include"]
            if item.get("from"):
                include = f"{item.get('from')}/{include}"
            result.append(include)
        result.extend(source.pop("include", []))
        return result

    @convert_from("exclude")
    def excludes(self, value):
        return value

    @convert_from("source")
    def source(self, value):
        self.settings["source"] = [
            {
                "name": item.get("name", ""),
                "url": item.get("url", ""),
                "verify_ssl": item.get("url", "").startswith("https"),
            }
            for item in value
        ]
        raise Unset()


def convert(project, filename):
    with open(filename, encoding="utf-8") as fp, cd(
        os.path.dirname(os.path.abspath(filename))
    ):
        converter = PoetryMetaConverter(toml.load(fp)["tool"]["poetry"])
        return dict(converter), converter.settings


def export(project, candidates, options):
    raise NotImplementedError()
