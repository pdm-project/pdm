from __future__ import annotations

import functools
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
        self._selected_source: RepositoryConfig | None = None

    def _get_new_credentials(
        self, original_url: str, *, allow_netrc: bool = True, allow_keyring: bool = False
    ) -> tuple[str | None, str | None]:
        user, password = super()._get_new_credentials(
            original_url, allow_netrc=allow_netrc, allow_keyring=allow_keyring
        )
        if (user is None or password is None) and allow_keyring and self._selected_source:
            self._selected_source.populate_keyring_auth()
            user = user or self._selected_source.username
            password = password or self._selected_source.password
        self._selected_source = None
        return user, password

    def _get_auth_from_index_url(self, url: str) -> tuple[MaybeAuth, str | None]:
        if not self.sources:
            return None, None

        target = urllib.parse.urlsplit(url.rstrip("/") + "/")
        candidates: list[tuple[MaybeAuth, str, urllib.parse.SplitResult, RepositoryConfig]] = []
        for source in self.sources:
            assert source.url
            index = source.url.rstrip("/") + "/"
            auth, url_no_auth = split_auth_from_url(index)
            parsed = urllib.parse.urlsplit(url_no_auth)
            if source.username:
                auth = (source.username, source.password)
            if parsed == target:
                return auth, index
            if parsed.netloc == target.netloc:
                candidates.append((auth, index, parsed, source))

        if not candidates:
            return None, None
        auth, index, _, source = max(candidates, key=lambda x: commonprefix(x[2].path, target.path).rfind("/"))
        self._selected_source = source
        return auth, index

    def _prompt_for_password(self, netloc: str, username: str | None = None) -> tuple[str | None, str | None, bool]:
        if self.ui.verbosity < Verbosity.DETAIL:
            raise PdmException(
                f"The credentials for {netloc} are not provided. To give them via interactive shell, "
                "please rerun the command with `-v` option."
            )
        return super()._prompt_for_password(netloc, username)

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

    @functools.lru_cache(maxsize=128)
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
