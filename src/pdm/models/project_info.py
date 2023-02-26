from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from email.message import Message
from typing import TYPE_CHECKING, Any, Iterator, cast

if TYPE_CHECKING:
    from pdm.compat import Distribution


DYNAMIC = "DYNAMIC"


@dataclass
class ProjectInfo:
    name: str
    version: str
    summary: str = ""
    author: str = ""
    email: str = ""
    license: str = ""
    requires_python: str = ""
    platform: str = ""
    keywords: str = ""
    homepage: str = ""
    project_urls: list[str] = field(default_factory=list)
    latest_stable_version: str = ""
    installed_version: str = ""

    @classmethod
    def from_distribution(cls, data: Distribution) -> ProjectInfo:
        metadata = cast(Message, data.metadata)
        keywords = metadata.get("Keywords", "").replace(",", ", ")
        platform = metadata.get("Platform", "").replace(",", ", ")

        if "Project-URL" in metadata:
            project_urls = {
                k.strip(): v.strip() for k, v in (row.split(",") for row in metadata.get_all("Project-URL", []))
            }
        else:
            project_urls = {}

        return cls(
            name=metadata["Name"],
            version=metadata["Version"],
            summary=metadata.get("Summary", ""),
            author=metadata.get("Author", ""),
            email=metadata.get("Author-email", ""),
            license=metadata.get("License", ""),
            requires_python=metadata.get("Requires-Python", ""),
            platform=platform,
            keywords=keywords,
            homepage=metadata.get("Home-page", ""),
            project_urls=[": ".join(parts) for parts in project_urls.items()],
        )

    @classmethod
    def from_metadata(cls, metadata: dict[str, Any]) -> ProjectInfo:
        def get_str(key: str) -> str:
            if key in metadata.get("dynamic", []):
                return DYNAMIC
            return metadata.get(key, "")

        authors = metadata.get("authors", [])
        author = authors[0]["name"] if authors else ""
        email = authors[0]["email"] if authors else ""

        return cls(
            name=metadata["name"],
            version=get_str("version"),
            summary=get_str("description"),
            author=author,
            email=email,
            license=metadata.get("license", {}).get("text", ""),
            requires_python=get_str("requires-python"),
            keywords=",".join(get_str("keywords")),
            project_urls=[": ".join(parts) for parts in metadata.get("urls", {}).items()],
        )

    def generate_rows(self) -> Iterator[tuple[str, str]]:
        yield "[primary]Name[/]:", self.name
        yield "[primary]Latest version[/]:", self.version
        if self.latest_stable_version:
            yield ("[primary]Latest stable version[/]:", self.latest_stable_version)
        if self.installed_version:
            yield ("[primary]Installed version[/]:", self.installed_version)
        yield "[primary]Summary[/]:", self.summary
        yield "[primary]Requires Python:", self.requires_python
        yield "[primary]Author[/]:", self.author
        yield "[primary]Author email[/]:", self.email
        yield "[primary]License[/]:", self.license
        yield "[primary]Homepage[/]:", self.homepage
        yield from itertools.zip_longest(("[primary]Project URLs[/]:",), self.project_urls, fillvalue="")
        yield "[primary]Platform[/]:", self.platform
        yield "[primary]Keywords[/]:", self.keywords
