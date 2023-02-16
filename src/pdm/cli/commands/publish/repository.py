from __future__ import annotations

import pathlib
import weakref
from typing import Any, Iterable
from urllib.parse import urlparse

import requests
import requests_toolbelt
import rich.progress

from pdm import termui
from pdm.cli.commands.publish.package import PackageFile
from pdm.exceptions import PdmUsageError
from pdm.project import Project
from pdm.project.config import DEFAULT_REPOSITORIES

try:
    import keyring
except ImportError:
    keyring = None


class Repository:
    def __init__(
        self,
        project: Project,
        url: str,
        username: str | None,
        password: str | None,
        ca_certs: str | None,
    ) -> None:
        self.url = url
        self.session = project.environment._build_session([], [])
        if ca_certs is not None:
            self.session.set_ca_certificates(pathlib.Path(ca_certs))
        self._credentials_to_save: tuple[str, str, str] | None = None
        username, password = self._ensure_credentials(username, password)
        self.session.auth = (username, password)
        weakref.finalize(self, self.session.close)
        self.ui = project.core.ui

    def _ensure_credentials(self, username: str | None, password: str | None) -> tuple[str, str]:
        netloc = urlparse(self.url).netloc
        if username and password:
            return username, password
        if not termui.is_interactive():
            raise PdmUsageError("Username and password are required")
        username, password, save = self._prompt_for_credentials(netloc, username)
        if save and keyring is not None and termui.confirm("Save credentials to keyring?"):
            self._credentials_to_save = (netloc, username, password)
        return username, password

    def _prompt_for_credentials(self, service: str, username: str | None) -> tuple[str, str, bool]:
        if keyring is not None:
            cred = keyring.get_credential(service, username)
            if cred is not None:
                return cred.username, cred.password, False
        if username is None:
            username = termui.ask("[primary]Username")
        password = termui.ask("[primary]Password", password=True)
        return username, password, True

    def _save_credentials(self, service: str, username: str, password: str) -> None:
        self.ui.echo("Saving credentials to keyring")
        keyring.set_password(service, username, password)

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
        return {f"{base}project/{package.metadata['name']}/{package.metadata['version']}/" for package in packages}

    def upload(self, package: PackageFile, progress: rich.progress.Progress) -> requests.Response:
        payload = package.metadata_dict
        payload.update(
            {
                ":action": "file_upload",
                "protocol_version": "1",
            }
        )
        field_parts = self._convert_to_list_of_tuples(payload)

        progress.live.console.print(f"Uploading [success]{package.base_filename}")

        with open(package.filename, "rb") as fp:
            field_parts.append(("content", (package.base_filename, fp, "application/octet-stream")))

            def on_upload(monitor: requests_toolbelt.MultipartEncoderMonitor) -> None:
                progress.update(job, completed=monitor.bytes_read)

            monitor = requests_toolbelt.MultipartEncoderMonitor.from_fields(field_parts, callback=on_upload)
            job = progress.add_task("", total=monitor.len)
            resp = self.session.post(
                self.url,
                data=monitor,
                headers={"Content-Type": monitor.content_type},
                allow_redirects=False,
            )
            if resp.status_code < 400 and self._credentials_to_save is not None:
                self._save_credentials(*self._credentials_to_save)
                self._credentials_to_save = None
            return resp
