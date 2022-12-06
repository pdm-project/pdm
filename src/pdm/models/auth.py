from __future__ import annotations

from unearth.auth import MultiDomainBasicAuth

from pdm._types import Source
from pdm.exceptions import PdmException
from pdm.termui import UI

try:
    import keyring
except ModuleNotFoundError:
    keyring = None  # type: ignore

ui = UI()


class PdmBasicAuth(MultiDomainBasicAuth):
    """A custom auth class that differs from Pip's implementation in the
    following ways:

        - It shows an error message when credentials are not provided or correct.
    """

    def __init__(
        self, prompting: bool = True, index_urls: list[str] | None = None
    ) -> None:
        super().__init__(prompting=True, index_urls=index_urls)
        self._real_prompting = prompting

    def _prompt_for_password(self, netloc: str) -> tuple[str | None, str | None, bool]:
        if not self._real_prompting:
            raise PdmException(
                f"The credentials for {netloc} are not provided. "
                "Please rerun the command with `-v` option."
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


def make_basic_auth(sources: list[Source], prompting: bool) -> PdmBasicAuth:
    return PdmBasicAuth(
        prompting,
        [source["url"] for source in sources if source.get("type", "index") == "index"],
    )
