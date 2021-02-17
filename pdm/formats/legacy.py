import functools

import toml

from pdm.formats.base import (
    MetaConverter,
    Unset,
    convert_from,
    make_array,
    make_inline_table,
    parse_name_email,
)
from pdm.models.requirements import Requirement


def check_fingerprint(project, filename):
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
    def authors(self, value):
        return parse_name_email([value])

    @convert_from("maintainer")
    def maintainers(self, value):
        return parse_name_email([value])

    @convert_from("version")
    def version(self, value):
        if not isinstance(value, str):
            self._data.setdefault("dynamic", []).append("version")
        return value

    @convert_from("python_requires", name="requires-python")
    def requires_python(self, value):
        if "classifiers" not in self._data.setdefault("dynamic", []):
            self._data["dynamic"].append("classifiers")
        return value

    @convert_from("license")
    def license(self, value):
        if "classifiers" not in self._data.setdefault("dynamic", []):
            self._data["dynamic"].append("classifiers")
        return make_inline_table({"text": value})

    @convert_from("source")
    def source(self, value):
        self.settings["source"] = value
        raise Unset()

    @convert_from("homepage")
    def homepage(self, value):
        self._data.setdefault("urls", {})["homepage"] = value
        raise Unset()

    @convert_from("project_urls")
    def urls(self, value):
        self._data.setdefault("urls", {}).update(value)
        raise Unset()

    @convert_from("dependencies")
    def dependencies(self, value):
        return make_array(
            [
                Requirement.from_req_dict(name, req).as_line()
                for name, req in value.items()
            ],
            True,
        )

    @convert_from("dev-dependencies", name="dev-dependencies")
    def dev_dependencies(self, value):
        return make_array(
            [
                Requirement.from_req_dict(name, req).as_line()
                for name, req in value.items()
            ],
            True,
        )

    @convert_from(name="optional-dependencies")
    def optional_dependencies(self, source):
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
    def scripts(self, value):
        return dict(value)

    @convert_from("entry_points", name="entry-points")
    def entry_points(self, value):
        return dict(value)

    @convert_from("scripts")
    def run_scripts(self, value):
        self.settings["scripts"] = value
        raise Unset()

    @convert_from("allow_prereleases")
    def allow_prereleases(self, value):
        self.settings["allow_prereleases"] = value
        raise Unset()


def convert(project, filename):
    with open(filename, encoding="utf-8") as fp:
        converter = LegacyMetaConverter(toml.load(fp)["tool"]["pdm"], filename)
        return dict(converter), converter.settings


def export(project, candidates, options):
    raise NotImplementedError()
