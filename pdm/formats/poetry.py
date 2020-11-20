import functools
import operator
import re

import tomlkit
import tomlkit.exceptions

from pdm.formats.base import MetaConverter, convert_from
from pdm.models.markers import Marker
from pdm.models.specifiers import PySpecSet


def check_fingerprint(project, filename):
    with open(filename, encoding="utf-8") as fp:
        try:
            data = tomlkit.parse(fp.read())
        except tomlkit.exceptions.TOMLKitError:
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
        return ""
    parts = [PySpecSet(_convert_specifier(s)) for s in python.split("||")]
    return functools.reduce(operator.or_, parts)


def _convert_req(req_dict):
    if not getattr(req_dict, "items", None):
        return _convert_specifier(req_dict)
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
    return req_dict


class PoetryMetaConverter(MetaConverter):
    @convert_from("authors")
    def author(self, value):
        return value[0]

    @convert_from("maintainers")
    def maintainer(self, value):
        return value[0]

    @convert_from()
    def python_requires(self, source):
        python = source.get("dependencies", {}).pop("python", None)
        return str(_convert_python(python))

    @convert_from()
    def project_urls(self, source):
        rv = source.pop("urls", {})
        if "repository" in source:
            rv["Repository"] = source.pop("repository")
        if "documentation" in source:
            rv["Documentation"] = source.pop("documentation")
        return rv

    @convert_from("scripts")
    def cli(self, value):
        return value

    @convert_from("plugins")
    def entry_points(self, value):
        return value

    @convert_from()
    def dependencies(self, source):
        rv = {}
        value, extras = dict(source["dependencies"]), source.pop("extras", {})
        for key, req_dict in value.items():
            optional = getattr(req_dict, "items", None) and req_dict.pop(
                "optional", False
            )
            req_dict = _convert_req(req_dict)
            if optional:
                extra = next((k for k, v in extras.items() if key in v), None)
                if extra:
                    self._data.setdefault(f"{extra}-dependencies", {})[key] = req_dict
            else:
                rv[key] = req_dict
        if extras:
            self._data["extras"] = list(extras)
        del source["dependencies"]
        return rv

    @convert_from("dev-dependencies", name="dev-dependencies")
    def dev_dependencies(self, value):
        return {key: _convert_req(req) for key, req in value.items()}

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


def convert(project, filename):
    with open(filename, encoding="utf-8") as fp:
        return dict(PoetryMetaConverter(tomlkit.parse(fp.read())["tool"]["poetry"]))


def export(project, candidates, options):
    raise NotImplementedError()
