from typing import Dict, Iterator, List, Tuple, Union, no_type_check

from pdm import termui


class ProjectInfo:
    def __init__(self, data: Dict[str, Union[str, List[str]]], legacy: bool) -> None:
        self._data = data
        self.legacy = legacy
        self.latest_stable_version = ""
        self.installed_version = ""

    @no_type_check
    def generate_rows(self) -> Iterator[Tuple[str, str]]:
        if self.legacy:
            yield from self._legacy_generate_rows()
            return
        yield termui.cyan("Name:"), self._data["name"]
        yield termui.cyan("Latest version:"), self._data["version"]
        if self.latest_stable_version:
            yield (termui.cyan("Latest stable version:"), self.latest_stable_version)
        if self.installed_version:
            yield (termui.green("Installed version:"), self.installed_version)
        yield termui.cyan("Summary:"), self._data.get("summary", "")
        contacts = (
            self._data.get("extensions", {}).get("python.details", {}).get("contacts")
        )
        if contacts:
            author_contact = next(
                iter(c for c in contacts if c["role"] == "author"), {}
            )
            yield termui.cyan("Author:"), author_contact.get("name", "")
            yield termui.cyan("Author email:"), author_contact.get("email", "")
        yield termui.cyan("License:"), self._data.get("license", "")
        yield termui.cyan("Homepage:"), self._data.get("extensions", {}).get(
            "python.details", {}
        ).get("project_urls", {}).get("Home", "")
        yield termui.cyan("Project URLs:"), self._data.get("project_url", "")
        yield termui.cyan("Platform:"), self._data.get("platform", "")
        yield termui.cyan("Keywords:"), ", ".join(self._data.get("keywords", []))

    @no_type_check
    def _legacy_generate_rows(self) -> Iterator[Tuple[str, str]]:
        yield termui.cyan("Name:"), self._data["Name"]
        yield termui.cyan("Latest version:"), self._data["Version"]
        if self.latest_stable_version:
            yield (termui.cyan("Latest stable version:"), self.latest_stable_version)
        if self.installed_version:
            yield (termui.green("Installed version:"), self.installed_version)
        yield termui.cyan("Summary:"), self._data.get("Summary", "")
        yield termui.cyan("Author:"), self._data.get("Author", "")
        yield termui.cyan("Author email:"), self._data.get("Author-email", "")
        yield termui.cyan("License:"), self._data.get("License", "")
        yield termui.cyan("Requires python:"), self._data.get("Requires-Python", "")
        yield termui.cyan("Platform:"), ", ".join(self._data.get("Platform", []))
        yield termui.cyan("Keywords:"), ", ".join(self._data.get("Keywords", []))
        yield termui.cyan("Homepage:"), self._data.get("Home-page", "")
        if self._data.get("Project-URL"):
            lines = [":".join(parts) for parts in self._data.get("Project-URL")]
            yield termui.cyan("Project URLs:"), lines[0]
            for line in lines[1:]:
                yield "", line
