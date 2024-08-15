from __future__ import annotations

import urllib.parse

from unearth.auth import MaybeAuth, MultiDomainBasicAuth, get_keyring_provider
from unearth.utils import commonprefix, split_auth_from_url

from pdm._types import RepositoryConfig
from pdm.exceptions import PdmException
from pdm.termui import UI, Verbosity, is_interactive


class PdmBasicAuth(MultiDomainBasicAuth):
    """A custom auth class that differs from Pip's implementation in the
    following ways:

        - It shows an error message when credentials are not provided or correct.
    """

    def __init__(self, ui: UI, sources: list[RepositoryConfig]) -> None:
        super().__init__(prompting=is_interactive())
        self.sources = sources
        self.ui = ui

    def _get_auth_from_index_url(self, url: str) -> tuple[MaybeAuth, str | None]:
        if not self.sources:
            return None, None

        target = urllib.parse.urlsplit(url.rstrip("/") + "/")
        candidates: list[tuple[MaybeAuth, str, urllib.parse.SplitResult]] = []
        for source in self.sources:
            assert source.url
            index = source.url.rstrip("/") + "/"
            auth, url_no_auth = split_auth_from_url(index)
            parsed = urllib.parse.urlparse(url_no_auth)
            if source.username:
                auth = (source.username, source.password)
            if parsed == target:
                return auth, index
            if parsed.netloc == target.netloc:
                candidates.append((auth, index, parsed))

        if not candidates:
            return None, None
        auth, index, _ = max(candidates, key=lambda x: commonprefix(x[2].path, target.path).rfind("/"))
        return auth, index

    def _prompt_for_password(self, netloc: str) -> tuple[str | None, str | None, bool]:
        if self.ui.verbosity < Verbosity.DETAIL:
            raise PdmException(
                f"The credentials for {netloc} are not provided. To give them via interactive shell, "
                "please rerun the command with `-v` option."
            )
        return super()._prompt_for_password(netloc)

    def _should_save_password_to_keyring(self) -> bool:
        if get_keyring_provider() is None:
            self.ui.info(
                "The provided credentials will not be saved into the keyring.\n"
                "You can enable this by installing keyring:\n"
                "    [success]pdm self add keyring[/]"
            )
        return super()._should_save_password_to_keyring()


class Keyring:
    def __init__(self) -> None:
        self.provider = get_keyring_provider()
        self.enabled = self.provider is not None

    def get_auth_info(self, url: str, username: str | None) -> tuple[str, str] | None:
        """Return the password for the given url and username.
        The username can be None.
        """
        if self.provider is None or not self.enabled:
            return None
        try:
            return self.provider.get_auth_info(url, username)
        except Exception:
            self.enabled = False
            return None

    def save_auth_info(self, url: str, username: str, password: str) -> bool:
        """Set the password for the given url and username.
        Returns whether the operation is successful.
        """
        if self.provider is None or not self.enabled:
            return False
        try:
            self.provider.save_auth_info(url, username, password)
            return True
        except Exception:
            self.enabled = False
            return False

    def delete_auth_info(self, url: str, username: str) -> bool:
        """Delete the password for the given url and username.
        Returns whether the operation is successful.
        """
        if self.provider is None or not self.enabled:
            return False
        try:
            self.provider.delete_auth_info(url, username)
            return True
        except Exception:
            self.enabled = False
            return False


keyring = Keyring()
