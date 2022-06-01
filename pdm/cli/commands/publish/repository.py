from __future__ import annotations

import atexit
from typing import Any, Iterable

import requests
import requests_toolbelt
import rich.progress

from pdm.cli.commands.publish.package import PackageFile
from pdm.models.session import PDMSession
from pdm.project import Project
from pdm.project.config import DEFAULT_REPOSITORIES


class Repository:
    def __init__(
        self, project: Project, url: str, username: str | None, password: str | None
    ) -> None:
        self.url = url
        self.session = PDMSession(cache_dir=project.cache("http"))
        self.session.auth = (
            (username or "", password or "") if username or password else None
        )
        self.ui = project.core.ui

        atexit.register(self.session.close)

    @staticmethod
    def _convert_to_list_of_tuples(data: dict[str, Any]) -> list[tuple[str, Any]]:
        result: list[tuple[str, Any]] = []
        for key, value in data.items():
            if isinstance(value, (list, tuple)) and key != "gpg_signature":
                for item in value:
                    result.append((key, item))
            else:
                result.append((key, value))
        return result

    def get_release_urls(self, packages: list[PackageFile]) -> Iterable[str]:
        if self.url.startswith(DEFAULT_REPOSITORIES["pypi"].url.rstrip("/")):
            base = "https://pypi.org/"
        elif self.url.startswith(DEFAULT_REPOSITORIES["testpypi"].url.rstrip("/")):
            base = "https://test.pypi.org/"
        else:
            return set()
        return {
            f"{base}project/{package.metadata['name']}/{package.metadata['version']}/"
            for package in packages
        }

    def upload(
        self, package: PackageFile, progress: rich.progress.Progress
    ) -> requests.Response:
        payload = package.metadata_dict
        payload.update(
            {
                ":action": "file_upload",
                "protocol_version": "1",
            }
        )
        field_parts = self._convert_to_list_of_tuples(payload)

        progress.live.console.print(f"Uploading [green]{package.base_filename}")

        with open(package.filename, "rb") as fp:
            field_parts.append(
                ("content", (package.base_filename, fp, "application/octet-stream"))
            )

            def on_upload(monitor: requests_toolbelt.MultipartEncoderMonitor) -> None:
                progress.update(job, completed=monitor.bytes_read)

            monitor = requests_toolbelt.MultipartEncoderMonitor.from_fields(
                field_parts, callback=on_upload
            )
            job = progress.add_task("", total=monitor.len)
            return self.session.post(
                self.url,
                data=monitor,
                headers={"Content-Type": monitor.content_type},
                allow_redirects=False,
            )
