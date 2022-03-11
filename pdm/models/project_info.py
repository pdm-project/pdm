from __future__ import annotations

import itertools
import sys
from typing import Any, Iterator

from pdm import termui
from pdm.pep517.metadata import Metadata

if sys.version_info >= (3, 8):
    from importlib.metadata import Distribution
else:
    from importlib_metadata import Distribution


class ProjectInfo:
    def __init__(self, metadata: Distribution | Metadata) -> None:
        self.latest_stable_version = ""
        self.installed_version = ""
        if isinstance(metadata, Metadata):
            self._parsed = self._parse_self(metadata)
        else:
            self._parsed = self._parse(metadata)

    def _parse(self, data: Distribution) -> dict[str, Any]:
        metadata = data.metadata
        keywords = metadata.get("Keywords", "").replace(",", ", ")
        platform = metadata.get("Platform", "").replace(",", ", ")
        project_urls = {
            k.strip(): v.strip()
            for k, v in (row.split(",") for row in metadata.get_all("Project-URL", []))
        }
        return {
            "name": metadata["Name"],
            "version": metadata["Version"],
            "summary": metadata.get("Summary", ""),
            "author": metadata.get("Author", ""),
            "email": metadata.get("Author-email", ""),
            "license": metadata.get("License", ""),
            "requires-python": metadata.get("Requires-Python", ""),
            "platform": platform,
            "keywords": keywords,
            "homepage": metadata.get("Home-page", ""),
            "project-urls": [": ".join(parts) for parts in project_urls.items()],
        }

    def _parse_self(self, metadata: Metadata) -> dict[str, Any]:
        license_expression = getattr(metadata, "license_expression", None)
        if license_expression is None:
            license_expression = getattr(metadata, "license", "")
        return {
            "name": str(metadata.name),
            "version": str(metadata.version),
            "summary": str(metadata.description),
            "author": str(metadata.author),
            "email": str(metadata.author_email),
            "license": license_expression,
            "requires-python": str(metadata.requires_python),
            "platform": "",
            "keywords": ", ".join(metadata.keywords or []),
            "homepage": "",
            "project-urls": [
                ": ".join(parts) for parts in (metadata.project_urls or {}).items()
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
        yield termui.cyan("Requires Python:"), self._parsed["requires-python"]
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
