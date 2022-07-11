from __future__ import annotations

import itertools
from email.message import Message
from typing import TYPE_CHECKING, Any, Iterator, cast

from pdm.pep517.metadata import Metadata

if TYPE_CHECKING:
    from pdm.compat import Distribution


class ProjectInfo:
    def __init__(self, metadata: Distribution | Metadata) -> None:
        self.latest_stable_version = ""
        self.installed_version = ""
        if isinstance(metadata, Metadata):
            self._parsed = self._parse_self(metadata)
        else:
            self._parsed = self._parse(metadata)

    def _parse(self, data: Distribution) -> dict[str, Any]:
        metadata = cast(Message, data.metadata)
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
            "license": str(license_expression),
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
        yield "[b cyan]Name[/]:", self._parsed["name"]
        yield "[b cyan]Latest version[/]:", self._parsed["version"]
        if self.latest_stable_version:
            yield ("[b cyan]Latest stable version[/]:", self.latest_stable_version)
        if self.installed_version:
            yield ("[b cyan]Installed version[/]:", self.installed_version)
        yield "[b cyan]Summary[/]:", self._parsed.get("summary", "")
        yield "[b cyan]Requires Python:", self._parsed["requires-python"]
        yield "[b cyan]Author[/]:", self._parsed.get("author", "")
        yield "[b cyan]Author email[/]:", self._parsed.get("email", "")
        yield "[b cyan]License[/]:", self._parsed.get("license", "")
        yield "[b cyan]Homepage[/]:", self._parsed.get("homepage", "")
        yield from itertools.zip_longest(
            ("[b cyan]Project URLs[/]:",),
            self._parsed.get("project-urls", []),
            fillvalue="",
        )
        yield "[b cyan]Platform[/]:", self._parsed.get("platform", "")
        yield "[b cyan]Keywords[/]:", self._parsed.get("keywords", "")
