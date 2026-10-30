from __future__ import annotations

import itertools
import string
from collections.abc import Iterator
from dataclasses import dataclass, field
from email.message import Message
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from importlib.metadata import Distribution


def normalize_project_url_label(label: str) -> str:
    # Project-URL label normalization from the core metadata spec
    chars_to_remove = string.punctuation + string.whitespace
    return label.translate(str.maketrans("", "", chars_to_remove)).lower()


_normalize_label = normalize_project_url_label


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

        # The label ends at the first comma, the URL itself may contain commas
        project_urls = {
            k.strip(): v.strip() for k, v in (row.split(",", 1) for row in metadata.get_all("Project-URL", []))
        }
        # Home-page is deprecated, PEP 621 projects only set a "Homepage" Project-URL
        homepage = metadata.get("Home-page") or next(
            (url for label, url in project_urls.items() if _normalize_label(label) == "homepage"), ""
        )

        return cls(
            name=metadata.get("Name", ""),
            version=metadata.get("Version", ""),
            summary=metadata.get("Summary", ""),
            author=metadata.get("Author", ""),
            email=metadata.get("Author-email", ""),
            # Core metadata 2.4 (PEP 639) puts an SPDX expression in License-Expression
            license=metadata.get("License-Expression") or metadata.get("License") or "",
            requires_python=metadata.get("Requires-Python", ""),
            platform=platform,
            keywords=keywords,
            homepage=homepage,
            project_urls=[": ".join(parts) for parts in project_urls.items()],
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
