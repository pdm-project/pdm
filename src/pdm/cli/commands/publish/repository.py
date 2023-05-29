from __future__ import annotations

import os
import pathlib
import weakref
from typing import TYPE_CHECKING, Any, Iterable
from urllib.parse import urlparse, urlunparse

import rich.progress

from pdm import termui
from pdm.cli.commands.publish.package import PackageFile
from pdm.exceptions import PdmUsageError
from pdm.project import Project
from pdm.project.config import DEFAULT_REPOSITORIES

if TYPE_CHECKING:
    from requests import Response


class Repository:
    def __init__(
        self,
        project: Project,
        url: str,
        username: str | None,
        password: str | None,
        ca_certs: str | None,
        verify_ssl: bool | None = True,
    ) -> None:
        self.url = url
        self.session = project.environment._build_session([])
        if verify_ssl is False:
            self.session.verify = verify_ssl
        elif ca_certs is not None:
            self.session.set_ca_certificates(pathlib.Path(ca_certs))
        self._credentials_to_save: tuple[str, str, str] | None = None
        self.ui = project.core.ui
        username, password = self._ensure_credentials(username, password)
        self.session.auth = (username, password)
        weakref.finalize(self, self.session.close)

    def _ensure_credentials(self, username: str | None, password: str | None) -> tuple[str, str]:
        from pdm.models.auth import keyring

        netloc = urlparse(self.url).netloc
        if username and password:
            return username, password
        if password:
            return "__token__", password
        if keyring.enabled:
            auth = keyring.get_auth_info(self.url, username)
            if auth is not None:
                return auth
        token = self._get_pypi_token_via_oidc()
        if token is not None:
            return "__token__", token
        if not termui.is_interactive():
            raise PdmUsageError("Username and password are required")
        username, password, save = self._prompt_for_credentials(netloc, username)
        if save and keyring.enabled and termui.confirm("Save credentials to keyring?"):
            self._credentials_to_save = (netloc, username, password)
        return username, password

    def _get_pypi_token_via_oidc(self) -> str | None:
        ACTIONS_ID_TOKEN_REQUEST_TOKEN = os.getenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
        ACTIONS_ID_TOKEN_REQUEST_URL = os.getenv("ACTIONS_ID_TOKEN_REQUEST_URL")
        if not ACTIONS_ID_TOKEN_REQUEST_TOKEN or not ACTIONS_ID_TOKEN_REQUEST_URL:
            return None
        self.ui.echo("Getting PyPI token via GitHub Actions OIDC...")
        import requests

        try:
            parsed_url = urlparse(self.url)
            audience_url = urlunparse(parsed_url._replace(path="/_/oidc/audience"))
            resp = self.session.get(audience_url)
            resp.raise_for_status()

            resp = self.session.get(
                ACTIONS_ID_TOKEN_REQUEST_URL,
                params=resp.json(),
                headers={"Authorization": f"bearer {ACTIONS_ID_TOKEN_REQUEST_TOKEN}"},
            )
            resp.raise_for_status()
            oidc_token = resp.json()["value"]

            mint_token_url = urlunparse(parsed_url._replace(path="/_/oidc/github/mint-token"))
            resp = self.session.post(mint_token_url, json={"token": oidc_token})
            resp.raise_for_status()
            token = resp.json()["token"]
        except requests.RequestException:
            self.ui.echo("Failed to get PyPI token via GitHub Actions OIDC", err=True)
            return None
        else:
            if os.getenv("GITHUB_ACTIONS"):
                # tell GitHub Actions to mask the token in any console logs
                print(f"::add-mask::{token}")
            return token

    def _prompt_for_credentials(self, service: str, username: str | None) -> tuple[str, str, bool]:
        from pdm.models.auth import keyring

        if keyring.enabled:
            cred = keyring.get_auth_info(service, username)
            if cred is not None:
                return cred[0], cred[1], False
        if username is None:
            username = termui.ask("[primary]Username")
        password = termui.ask("[primary]Password", password=True)
        return username, password, True

    def _save_credentials(self, service: str, username: str, password: str) -> None:
        from pdm.models.auth import keyring

        self.ui.echo("Saving credentials to keyring")
        keyring.save_auth_info(service, username, password)

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
        if self.url.startswith(DEFAULT_REPOSITORIES["pypi"].rstrip("/")):
            base = "https://pypi.org/"
        elif self.url.startswith(DEFAULT_REPOSITORIES["testpypi"].rstrip("/")):
            base = "https://test.pypi.org/"
        else:
            return set()
        return {f"{base}project/{package.metadata['name']}/{package.metadata['version']}/" for package in packages}

    def upload(self, package: PackageFile, progress: rich.progress.Progress) -> Response:
        import requests_toolbelt

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
