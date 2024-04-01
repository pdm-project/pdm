from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Iterable, cast
from urllib.parse import urlparse, urlunparse

import httpx
from rich.progress import BarColumn, DownloadColumn, TimeRemainingColumn, TransferSpeedColumn

from pdm import termui
from pdm.cli.commands.publish.package import PackageFile
from pdm.exceptions import PdmUsageError
from pdm.project import Project
from pdm.project.config import DEFAULT_REPOSITORIES

if TYPE_CHECKING:
    from typing import Callable, Self

    from httpx import Response
    from httpx._multipart import MultipartStream

    from pdm._types import RepositoryConfig


class CallbackWrapperStream(httpx.SyncByteStream):
    def __init__(self, stream: httpx.SyncByteStream, callback: Callable[[Self], Any]) -> None:
        self._stream = stream
        self._callback = callback
        self.bytes_read = 0

    def __iter__(self) -> Iterable[bytes]:
        for chunk in self._stream:
            self.bytes_read += len(chunk)
            self._callback(self)
            yield chunk


class Repository:
    def __init__(self, project: Project, config: RepositoryConfig) -> None:
        self.url = cast(str, config.url)
        self.session = project.environment._build_session([config])

        self._credentials_to_save: tuple[str, str, str] | None = None
        self.ui = project.core.ui
        username, password = self._ensure_credentials(config.username, config.password)
        self.session.auth = (username, password)

    def _ensure_credentials(self, username: str | None, password: str | None) -> tuple[str, str]:
        from pdm.models.auth import keyring

        parsed_url = urlparse(self.url)
        netloc = parsed_url.netloc
        if username and password:
            return username, password
        if password:
            return "__token__", password
        if parsed_url.username is not None and parsed_url.password is not None:
            return parsed_url.username, parsed_url.password
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
        import httpx

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
        except httpx.HTTPError:
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

    def upload(self, package: PackageFile) -> Response:
        data_fields = package.metadata_dict
        data_fields.update(
            {
                ":action": "file_upload",
                "protocol_version": "1",
            }
        )
        with self.ui.make_progress(
            " [progress.percentage]{task.percentage:>3.0f}%",
            BarColumn(),
            DownloadColumn(),
            "•",
            TimeRemainingColumn(
                compact=True,
                elapsed_when_finished=True,
            ),
            "•",
            TransferSpeedColumn(),
        ) as progress:
            progress.console.print(f"Uploading [success]{package.base_filename}")

            with open(package.filename, "rb") as fp:
                file_fields = [("content", (package.base_filename, fp, "application/octet-stream"))]

                def on_upload(monitor: CallbackWrapperStream) -> None:
                    progress.update(job, completed=monitor.bytes_read)

                request = self.session.build_request("POST", self.url, data=data_fields, files=file_fields)
                stream = cast("MultipartStream", request.stream)
                request.stream = CallbackWrapperStream(stream, on_upload)

                job = progress.add_task("", total=stream.get_content_length())
                resp = self.session.send(request, follow_redirects=False)
                if not resp.is_error and self._credentials_to_save is not None:
                    self._save_credentials(*self._credentials_to_save)
                    self._credentials_to_save = None
                return resp
