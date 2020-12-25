from typing import Dict, Iterator, List, Tuple, Union

from pdm.iostream import stream


class ProjectInfo:
    def __init__(self, data: Dict[str, Union[str, List[str]]], legacy: bool) -> None:
        self._data = data
        self.legacy = legacy
        self.latest_stable_version = ""
        self.installed_version = ""

    def generate_rows(self) -> Iterator[Tuple[str, str]]:
        if self.legacy:
            yield from self._legacy_generate_rows()
            return
        yield stream.cyan("Name:"), self._data["name"]
        yield stream.cyan("Latest version:"), self._data["version"]
        if self.latest_stable_version:
            yield (stream.cyan("Latest stable version:"), self.latest_stable_version)
        if self.installed_version:
            yield (stream.green("Installed version:"), self.installed_version)
        yield stream.cyan("Summary:"), self._data.get("summary", "")
        contacts = (
            self._data.get("extensions", {}).get("python.details", {}).get("contacts")
        )
        if contacts:
            author_contact = next(
                iter(c for c in contacts if c["role"] == "author"), {}
            )
            yield stream.cyan("Author:"), author_contact.get("name", "")
            yield stream.cyan("Author email:"), author_contact.get("email", "")
        yield stream.cyan("License:"), self._data.get("license", "")
        yield stream.cyan("Homepage:"), self._data.get("extensions", {}).get(
            "python.details", {}
        ).get("project_urls", {}).get("Home", "")
        yield stream.cyan("Project URLs:"), self._data.get("project_url", "")
        yield stream.cyan("Platform:"), self._data.get("platform", "")
        yield stream.cyan("Keywords:"), ", ".join(self._data.get("keywords", []))

    def _legacy_generate_rows(self) -> Iterator[Tuple[str, str]]:
        yield stream.cyan("Name:"), self._data["Name"]
        yield stream.cyan("Latest version:"), self._data["Version"]
        if self.latest_stable_version:
            yield (stream.cyan("Latest stable version:"), self.latest_stable_version)
        if self.installed_version:
            yield (stream.green("Installed version:"), self.installed_version)
        yield stream.cyan("Summary:"), self._data.get("Summary", "")
        yield stream.cyan("Author:"), self._data.get("Author", "")
        yield stream.cyan("Author email:"), self._data.get("Author-email", "")
        yield stream.cyan("License:"), self._data.get("License", "")
        yield stream.cyan("Requires python:"), self._data.get("Requires-Python", "")
        yield stream.cyan("Platform:"), ", ".join(self._data.get("Platform", []))
        yield stream.cyan("Keywords:"), ", ".join(self._data.get("Keywords", []))
        yield stream.cyan("Homepage:"), self._data.get("Home-page", "")
        if self._data.get("Project-URL"):
            lines = [":".join(parts) for parts in self._data.get("Project-URL")]
            yield stream.cyan("Project URLs:"), lines[0]
            for line in lines[1:]:
                yield "", line
