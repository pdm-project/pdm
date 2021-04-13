from __future__ import annotations

import functools
import operator
import os
import re
from argparse import Namespace
from os import PathLike
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Tuple, Union

import toml

from pdm._types import RequirementDict, Source
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

if TYPE_CHECKING:
    from pdm.project.core import Project

from pdm.utils import cd


def check_fingerprint(project: Optional[Project], filename: PathLike) -> bool:
    with open(filename, encoding="utf-8") as fp:
        try:
            data = toml.load(fp)
        except toml.TomlDecodeError:
            return False

    return "tool" in data and "poetry" in data["tool"]


VERSION_RE = re.compile(r"([^\d\s]*)\s*(\d.*?)\s*(?=,|$)")


def _convert_specifier(version: str) -> str:
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


def _convert_python(python: str) -> PySpecSet:
    if not python:
        return PySpecSet()
    parts = [PySpecSet(_convert_specifier(s)) for s in python.split("||")]
    return functools.reduce(operator.or_, parts)


def _convert_req(name: str, req_dict: RequirementDict) -> str:
    if not getattr(req_dict, "items", None):
        assert isinstance(req_dict, str)
        return Requirement.from_req_dict(name, _convert_specifier(req_dict)).as_line()
    assert isinstance(req_dict, dict)
    req_dict = dict(req_dict)
    if "version" in req_dict:
        req_dict["version"] = _convert_specifier(str(req_dict["version"]))
    markers = []
    if "markers" in req_dict:
        markers.append(Marker(req_dict.pop("markers")))
    if "python" in req_dict:
        markers.append(
            Marker(_convert_python(str(req_dict.pop("python"))).as_marker_string())
        )
    if markers:
        req_dict["marker"] = str(functools.reduce(operator.and_, markers)).replace(
            '"', "'"
        )
    if "rev" in req_dict or "branch" in req_dict or "tag" in req_dict:
        req_dict["ref"] = req_dict.pop(
            "rev", req_dict.pop("tag", req_dict.pop("branch", None))  # type: ignore
        )
    return Requirement.from_req_dict(name, req_dict).as_line()


class PoetryMetaConverter(MetaConverter):
    @convert_from("authors")
    def authors(self, value: List[str]) -> List[str]:
        return parse_name_email(value)

    @convert_from("maintainers")
    def maintainers(self, value: List[str]) -> List[str]:
        return parse_name_email(value)

    @convert_from("license")
    def license(self, value: str) -> Dict[str, str]:
        self._data["dynamic"] = ["classifiers"]
        return make_inline_table({"text": value})

    @convert_from(name="requires-python")
    def requires_python(self, source: Dict[str, Any]) -> str:
        python = source.get("dependencies", {}).pop("python", None)
        self._data["dynamic"] = ["classifiers"]
        return str(_convert_python(python))

    @convert_from()
    def urls(self, source: Dict[str, Any]) -> Dict[str, str]:
        rv = source.pop("urls", {})
        if "homepage" in source:
            rv["homepage"] = source.pop("homepage")
        if "repository" in source:
            rv["repository"] = source.pop("repository")
        if "documentation" in source:
            rv["documentation"] = source.pop("documentation")
        return rv

    @convert_from("plugins", name="entry-points")
    def entry_points(
        self, value: Dict[str, Dict[str, str]]
    ) -> Dict[str, Dict[str, str]]:
        return value

    @convert_from()
    def dependencies(self, source: Dict[str, Any]) -> List[str]:
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

    @convert_from("dev-dependencies")
    def dev_dependencies(self, value: dict) -> None:
        self.settings["dev-dependencies"] = {
            "dev": make_array(
                [_convert_req(key, req) for key, req in value.items()], True
            ),
        }
        raise Unset()

    @convert_from()
    def includes(self, source: Dict[str, Union[List[str], str]]) -> List[str]:
        result: List[str] = []
        for item in source.pop("packages", []):
            assert isinstance(item, dict)
            include = item["include"]
            if item.get("from"):
                include = f"{item.get('from')}/{include}"
            result.append(include)
        result.extend(source.pop("include", []))
        self.settings["includes"] = result
        raise Unset()

    @convert_from("exclude")
    def excludes(self, value: List[str]) -> None:
        self.settings["excludes"] = value
        raise Unset()

    @convert_from("build")
    def build(self, value: str) -> None:
        self.settings["build"] = value
        raise Unset()

    @convert_from("source")
    def sources(self, value: List[Source]) -> None:
        self.settings["source"] = [
            {
                "name": item.get("name", ""),
                "url": item.get("url", ""),
                "verify_ssl": item.get("url", "").startswith("https"),
            }
            for item in value
        ]
        raise Unset()


def convert(
    project: Optional[Project],
    filename: PathLike,
    options: Optional[Namespace],
) -> Tuple[Mapping[str, Any], Mapping[str, Any]]:
    with open(filename, encoding="utf-8") as fp, cd(
        os.path.dirname(os.path.abspath(filename))
    ):
        converter = PoetryMetaConverter(
            toml.load(fp)["tool"]["poetry"], project.core.ui if project else None
        )
        return converter.convert()


def export(project: Project, candidates: List, options: Optional[Any]) -> None:
    raise NotImplementedError()
