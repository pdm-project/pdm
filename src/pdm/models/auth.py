from __future__ import annotations

import urllib.parse

from unearth.auth import MaybeAuth, MultiDomainBasicAuth
from unearth.utils import split_auth_from_netloc

from pdm._types import Source
from pdm.exceptions import PdmException
from pdm.termui import UI

try:
    import keyring
except ModuleNotFoundError:
    keyring = None

ui = UI()


class PdmBasicAuth(MultiDomainBasicAuth):
    """A custom auth class that differs from Pip's implementation in the
    following ways:

        - It shows an error message when credentials are not provided or correct.
    """

    def __init__(self, sources: list[Source], prompting: bool = True) -> None:
        super().__init__(prompting=True)
        self._real_prompting = prompting
        self.sources = sources

    def _get_auth_from_index_url(self, netloc: str) -> tuple[MaybeAuth, str | None]:
        if not self.sources:
            return None, None
        for source in self.sources:
            parsed = urllib.parse.urlparse(source["url"])
            auth, index_netloc = split_auth_from_netloc(parsed.netloc)
            if index_netloc == netloc:
                if "username" in source:
                    auth = (source["username"], source.get("password"))
                return auth, source["url"]
        return None, None

    def _prompt_for_password(self, netloc: str) -> tuple[str | None, str | None, bool]:
        if not self._real_prompting:
            raise PdmException(
                f"The credentials for {netloc} are not provided. Please rerun the command with `-v` option."
            )
        return super()._prompt_for_password(netloc)

    def _should_save_password_to_keyring(self) -> bool:
        if keyring is None:
            ui.echo(
                "The provided credentials will not be saved into your system.\n"
                "You can enable this by installing keyring:\n"
                "    pdm self add keyring",
                err=True,
                style="warning",
            )
        return super()._should_save_password_to_keyring()
