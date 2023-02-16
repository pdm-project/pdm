from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path

import requests

PROJECT_DIR = Path(__file__).parent.parent


class PythonVersionParser(HTMLParser):
    def __init__(self, *, convert_charrefs: bool = True) -> None:
        super().__init__(convert_charrefs=convert_charrefs)
        self._parsing_release_number_span = False
        self._parsing_release_number_a = False
        self.parsed_python_versions: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str]]) -> None:
        if tag == "span" and any("release-number" in value for key, value in attrs if key == "class"):
            self._parsing_release_number_span = True
            return

        if self._parsing_release_number_span and tag == "a":
            self._parsing_release_number_a = True

    def handle_endtag(self, tag: str) -> None:
        if self._parsing_release_number_span and tag == "span":
            self._parsing_release_number_span = False

        if self._parsing_release_number_a and tag == "a":
            self._parsing_release_number_a = False

    def handle_data(self, data: str) -> None:
        if self._parsing_release_number_a:
            self.parsed_python_versions.append(data[7:])


def dump_python_version_module(dest_file) -> None:
    resp = requests.get("https://python.org/downloads")
    resp_text = resp.text
    parser = PythonVersionParser()
    parser.feed(resp_text)
    python_versions = sorted(parser.parsed_python_versions)
    max_versions: dict[str, int] = {}
    for version in python_versions:
        major, minor, patch = version.split(".")
        major_minor = f"{major}.{minor}"
        if major not in max_versions or max_versions[major] < int(minor):
            max_versions[major] = int(minor)
        if major_minor not in max_versions or max_versions[major_minor] < int(patch):
            max_versions[major_minor] = int(patch)
    with open(dest_file, "w") as f:
        json.dump(max_versions, f, sort_keys=True, indent=4)
        f.write("\n")


if __name__ == "__main__":
    dump_python_version_module(PROJECT_DIR / "src/pdm/models/python_max_versions.json")
