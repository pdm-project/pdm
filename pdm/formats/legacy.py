import functools
from argparse import Namespace
from os import PathLike
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

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
from pdm.models.requirements import Requirement
from pdm.project.core import Project


def check_fingerprint(project: Project, filename: PathLike) -> bool:
    with open(filename, encoding="utf-8") as fp:
        try:
            data = toml.load(fp)
        except toml.TomlDecodeError:
            return False

    return (
        "tool" in data
        and "pdm" in data["tool"]
        and "dependencies" in data["tool"]["pdm"]
    )


class LegacyMetaConverter(MetaConverter):
    @convert_from("author")
    def authors(self, value: str) -> List[str]:
        return parse_name_email([value])

    @convert_from("maintainer")
    def maintainers(self, value: List[str]) -> List[str]:
        return parse_name_email([value])

    @convert_from("version")
    def version(
        self, value: Union[Dict[str, str], List[str], str]
    ) -> Union[Dict[str, str], List[str], str]:
        if not isinstance(value, str):
            self._data.setdefault("dynamic", []).append("version")
        return value

    @convert_from("python_requires", name="requires-python")
    def requires_python(self, value: str) -> str:
        if "classifiers" not in self._data.setdefault("dynamic", []):
            self._data["dynamic"].append("classifiers")
        return value

    @convert_from("license")
    def license(self, value: str) -> Dict[str, str]:
        if "classifiers" not in self._data.setdefault("dynamic", []):
            self._data["dynamic"].append("classifiers")
        return make_inline_table({"text": value})

    @convert_from("source")
    def source(self, value: List[Source]) -> None:
        self.settings["source"] = value
        raise Unset()

    @convert_from("homepage")
    def homepage(self, value: str) -> None:
        self._data.setdefault("urls", {})["homepage"] = value
        raise Unset()

    @convert_from("project_urls")
    def urls(self, value: str) -> None:
        self._data.setdefault("urls", {}).update(value)
        raise Unset()

    @convert_from("dependencies")
    def dependencies(self, value: Dict[str, str]) -> List[str]:
        return make_array(
            [
                Requirement.from_req_dict(name, req).as_line()
                for name, req in value.items()
            ],
            True,
        )

    @convert_from("dev-dependencies")
    def dev_dependencies(self, value: Dict[str, RequirementDict]) -> None:
        self.settings["dev-dependencies"] = {
            "dev": make_array(
                [
                    Requirement.from_req_dict(name, req).as_line()
                    for name, req in value.items()
                ],
                True,
            )
        }
        raise Unset()

    @convert_from(name="optional-dependencies")
    def optional_dependencies(self, source: Dict[str, str]) -> Dict[str, str]:
        extras = {}
        for key, reqs in list(source.items()):
            if key.endswith("-dependencies") and key != "dev-dependencies":
                extra_key = key.split("-", 1)[0]
                extras[extra_key] = [
                    Requirement.from_req_dict(name, req).as_line()
                    for name, req in reqs.items()
                ]
                source.pop(key)
        for name in source.pop("extras", []):
            if name in extras:
                continue
            if "=" in name:
                key, parts = name.split("=", 1)
                parts = parts.split("|")
                extras[key] = list(
                    functools.reduce(lambda x, y: x.union(extras[y]), parts, set())
                )
        return extras

    @convert_from("cli")
    def scripts(self, value: str) -> Dict[str, str]:
        return dict(value)

    @convert_from("includes")
    def includes(self, value):
        self.settings["includes"] = value
        raise Unset()

    @convert_from("excludes")
    def excludes(self, value):
        self.settings["excludes"] = value
        raise Unset()

    @convert_from("build")
    def build(self, value):
        self.settings["build"] = value
        raise Unset()

    @convert_from("entry_points", name="entry-points")
    def entry_points(self, value: str) -> Dict[str, str]:
        return dict(value)

    @convert_from("scripts")
    def run_scripts(self, value: str) -> None:
        self.settings["scripts"] = value
        raise Unset()

    @convert_from("allow_prereleases")
    def allow_prereleases(self, value: bool) -> None:
        self.settings["allow_prereleases"] = value
        raise Unset()


def convert(
    project: Project, filename: Path, options: Optional[Namespace]
) -> Tuple[Dict[str, Any], Dict[str, List[Dict[str, Any]]]]:
    with open(filename, encoding="utf-8") as fp:
        converter = LegacyMetaConverter(toml.load(fp)["tool"]["pdm"], project.core.ui)
        return converter.convert()


def export(project: Project, candidates: List, options: Optional[Any]) -> None:
    raise NotImplementedError()
