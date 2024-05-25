from __future__ import annotations

import functools
import operator
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Mapping, cast

from pdm.compat import tomllib
from pdm.formats.base import (
    MetaConverter,
    Unset,
    array_of_inline_tables,
    convert_from,
    make_array,
    make_inline_table,
)
from pdm.models.markers import Marker, get_marker
from pdm.models.requirements import FileRequirement, Requirement
from pdm.models.specifiers import PySpecSet
from pdm.utils import cd

if TYPE_CHECKING:
    from argparse import Namespace

    from pdm._types import RequirementDict
    from pdm.project import Project


def check_fingerprint(project: Project | None, filename: Path | str) -> bool:
    if Path(filename).name != "pyproject.toml":
        return False
    with open(filename, "rb") as fp:
        try:
            data = tomllib.load(fp)
        except tomllib.TOMLDecodeError:
            return False

    return "tool" in data and "poetry" in data["tool"]


VERSION_RE = re.compile(r"([^\d\s]*)\s*(\d.*?)\s*(?=,|$)")


def _convert_specifier(version: str) -> str:
    parts = []
    for op, ver in VERSION_RE.findall(str(version)):
        if op == "~":
            op += "="
        elif op == "^":
            major, *vparts = ver.split(".")
            next_major = ".".join([str(int(major) + 1)] + ["0"] * len(vparts))
            parts.append(f">={ver},<{next_major}")
            continue
        elif not op:
            op = "=="
        parts.append(f"{op}{ver}")
    return ",".join(parts)


def _convert_python(python: str) -> PySpecSet:
    if not python:
        return PySpecSet()
    parts = [PySpecSet(_convert_specifier(s)) for s in python.split("||")]
    return functools.reduce(operator.or_, parts)


def _convert_req(name: str, req_dict: RequirementDict | list[RequirementDict]) -> Iterable[str]:
    from pdm.models.backends import DEFAULT_BACKEND

    backend = DEFAULT_BACKEND(Path.cwd())

    def fix_req_path(req: Requirement) -> Requirement:
        if isinstance(req, FileRequirement):
            req.relocate(backend)
        return req

    if isinstance(req_dict, list):
        for req in req_dict:
            yield from _convert_req(name, req)
    elif isinstance(req_dict, str):
        pdm_req = fix_req_path(Requirement.from_req_dict(name, _convert_specifier(req_dict), check_installable=False))
        yield pdm_req.as_line()
    else:
        assert isinstance(req_dict, dict)
        req_dict = dict(req_dict)
        req_dict.pop("optional", None)  # Ignore the 'optional' key
        if "version" in req_dict:
            req_dict["version"] = _convert_specifier(str(req_dict["version"]))
        markers: list[Marker] = []
        if "markers" in req_dict:
            markers.append(get_marker(req_dict.pop("markers")))  # type: ignore[arg-type]
        if "python" in req_dict:
            markers.append(get_marker(_convert_python(str(req_dict.pop("python"))).as_marker_string()))
        if markers:
            req_dict["marker"] = str(functools.reduce(operator.and_, markers)).replace('"', "'")
        if "rev" in req_dict or "branch" in req_dict or "tag" in req_dict:
            req_dict["ref"] = req_dict.pop(
                "rev",
                req_dict.pop("tag", req_dict.pop("branch", None)),  # type: ignore[arg-type]
            )
        pdm_req = fix_req_path(Requirement.from_req_dict(name, req_dict, check_installable=False))
        yield pdm_req.as_line()


# See https://github.com/python-poetry/poetry-core/pull/521#issuecomment-1327689551
# for reasoning why email.utils.parseaddr is not used here.
NAME_EMAIL_RE = re.compile(
    r"^(?P<name>[- .,\w'’\"():&]+)(?: <(?P<email>.+?)>)?$",  # noqa: RUF001
    re.UNICODE,
)


def parse_name_email(name_email: list[str]) -> list[str]:
    return array_of_inline_tables(
        [
            {
                k: v
                for k, v in NAME_EMAIL_RE.match(item).groupdict().items()  # type: ignore[union-attr]
                if v is not None
            }
            for item in name_email
        ]
    )


class PoetryMetaConverter(MetaConverter):
    @convert_from("authors")
    def authors(self, value: list[str]) -> list[str]:
        return parse_name_email(value)

    @convert_from("maintainers")
    def maintainers(self, value: list[str]) -> list[str]:
        return parse_name_email(value)

    @convert_from("license")
    def license(self, value: str) -> dict[str, str]:
        return make_inline_table({"text": value})

    @convert_from(name="requires-python")
    def requires_python(self, source: dict[str, Any]) -> str:
        python = source.get("dependencies", {}).pop("python", None)
        return str(_convert_python(python))

    @convert_from()
    def urls(self, source: dict[str, Any]) -> dict[str, str]:
        rv = source.pop("urls", {})
        if "homepage" in source:
            rv["homepage"] = source.pop("homepage")
        if "repository" in source:
            rv["repository"] = source.pop("repository")
        if "documentation" in source:
            rv["documentation"] = source.pop("documentation")
        return rv

    @convert_from("plugins", name="entry-points")
    def entry_points(self, value: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
        return value

    @convert_from()
    def dependencies(self, source: dict[str, Any]) -> list[str]:
        rv = []
        value, extras = dict(source["dependencies"]), source.pop("extras", {})
        for key, req_dict in value.items():
            optional = getattr(req_dict, "items", None) and req_dict.pop("optional", False)
            for req in _convert_req(key, req_dict):
                if optional:
                    extra = next((k for k, v in extras.items() if key in v), None)
                    if extra:
                        self._data.setdefault("optional-dependencies", {}).setdefault(extra, []).append(req)
                else:
                    rv.append(req)
        del source["dependencies"]
        return make_array(rv, True)

    @convert_from("dev-dependencies")
    def dev_dependencies(self, value: dict) -> None:
        self.settings.setdefault("dev-dependencies", {})["dev"] = make_array(
            [r for key, req in value.items() for r in _convert_req(key, req)], True
        )
        raise Unset()

    @convert_from("group")
    def group_dependencies(self, value: dict[str, dict[str, Any]]) -> None:
        for name, group in value.items():
            self.settings.setdefault("dev-dependencies", {})[name] = make_array(
                [r for key, req in group.get("dependencies", {}).items() for r in _convert_req(key, req)], True
            )
        raise Unset()

    @convert_from()
    def includes(self, source: dict[str, list[str] | str]) -> list[str]:
        includes: list[str] = []
        source_includes: list[str] = []
        for item in source.pop("packages", []):
            assert isinstance(item, dict)
            include = item["include"]
            if item.get("from"):
                include = Path(str(item.get("from")), include).as_posix()
            includes.append(include)
        for item in source.pop("include", []):
            if not isinstance(item, dict):
                includes.append(item)
            else:
                dest = source_includes if "sdist" in item.get("format", "") else includes
                dest.append(item["path"])
        self.settings.setdefault("build", {})["includes"] = includes
        raise Unset()

    @convert_from("exclude")
    def excludes(self, value: list[str]) -> None:
        self.settings.setdefault("build", {})["excludes"] = value
        raise Unset()

    @convert_from("build")
    def build(self, value: str | dict) -> None:
        value = {}
        if isinstance(value, dict):
            if "generate-setup-file" in value:
                value["run-setuptools"] = cast(bool, value["generate-setup-file"])
        self.settings.setdefault("build", {}).update(value)
        raise Unset()

    @convert_from("source")
    def sources(self, value: list[dict[str, Any]]) -> None:
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
    project: Project | None,
    filename: str | Path,
    options: Namespace | None,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    with open(filename, "rb") as fp, cd(os.path.dirname(os.path.abspath(filename))):
        converter = PoetryMetaConverter(tomllib.load(fp)["tool"]["poetry"], project.core.ui if project else None)
        return converter.convert()


def export(project: Project, candidates: list, options: Any) -> None:
    raise NotImplementedError()
