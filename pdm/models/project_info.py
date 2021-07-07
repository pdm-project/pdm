from __future__ import annotations

import itertools
from typing import Any, Iterator

from distlib.metadata import Metadata as DistMeta

from pdm import termui
from pdm.pep517.metadata import Metadata


class ProjectInfo:
    def __init__(self, metadata: DistMeta | Metadata) -> None:
        self.latest_stable_version = ""
        self.installed_version = ""
        if isinstance(metadata, Metadata):
            self._parsed = self._parse_self(metadata)
        elif metadata._legacy:
            self._parsed = self._parse_legacy(
                dict(metadata._legacy.items())  # type: ignore
            )
        else:
            self._parsed = self._parse(dict(metadata._data))  # type: ignore

    def _parse(self, data: dict[str, Any]) -> dict[str, Any]:
        result = {
            "name": data["name"],
            "version": data["version"],
            "summary": data.get("summary", ""),
            "license": data.get("license", ""),
            "homepage": data.get("extensions", {})
            .get("python.details", {})
            .get("project_urls", {})
            .get("Home", ""),
            "project_urls": [data.get("project_url", "")],
            "platform": data.get("platform", ""),
            "keywords": ", ".join(data.get("keywords", [])),
        }
        contacts = data.get("extensions", {}).get("python.details", {}).get("contacts")
        if contacts:
            author_contact: dict[str, Any] = next(
                iter(c for c in contacts if c["role"] == "author"), {}
            )
            result.update(
                author=author_contact.get("name", ""),
                email=author_contact.get("email", ""),
            )
        return result

    def _parse_legacy(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": data["Name"],
            "version": data["Version"],
            "summary": data.get("Summary", ""),
            "author": data.get("Author", ""),
            "email": data.get("Author-email", ""),
            "license": data.get("License", ""),
            "requires-python": data.get("Requires-Python", ""),
            "platform": ", ".join(data.get("Platform", [])),
            "keywords": ", ".join(data.get("Keywords", [])),
            "homepage": data.get("Home-page", ""),
            "project-urls": [": ".join(parts) for parts in data.get("Project-URL", [])],
        }

    def _parse_self(self, metadata: Metadata) -> dict[str, Any]:
        return {
            "name": str(metadata.name),
            "version": str(metadata.version),
            "summary": str(metadata.description),
            "author": str(metadata.author),
            "email": str(metadata.author_email),
            "license": str(metadata.license),
            "requires-python": str(metadata.requires_python),
            "platform": "",
            "keywords": ", ".join(metadata.keywords or []),
            "homepage": "",
            "project-urls": [
                ": ".join(parts) for parts in metadata.project_urls.items()
            ],
        }

    def __getitem__(self, key: str) -> Any:
        return self._parsed[key]

    def generate_rows(self) -> Iterator[tuple[str, str]]:
        yield termui.cyan("Name:"), self._parsed["name"]
        yield termui.cyan("Latest version:"), self._parsed["version"]
        if self.latest_stable_version:
            yield (termui.cyan("Latest stable version:"), self.latest_stable_version)
        if self.installed_version:
            yield (termui.green("Installed version:"), self.installed_version)
        yield termui.cyan("Summary:"), self._parsed.get("summary", "")
        yield termui.cyan("Author:"), self._parsed.get("author", "")
        yield termui.cyan("Author email:"), self._parsed.get("email", "")
        yield termui.cyan("License:"), self._parsed.get("license", "")
        yield termui.cyan("Homepage:"), self._parsed.get("homepage", "")
        yield from itertools.zip_longest(
            (termui.cyan("Project URLs:"),),
            self._parsed.get("project-urls", []),
            fillvalue="",
        )
        yield termui.cyan("Platform:"), self._parsed.get("platform", "")
        yield termui.cyan("Keywords:"), self._parsed.get("keywords", "")
