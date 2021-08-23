from typing import List, Optional, Tuple

import click

from pdm._types import Source
from pdm.exceptions import PdmException
from pdm.models.pip_shims import MultiDomainBasicAuth

try:
    import keyring
except ModuleNotFoundError:
    keyring = None  # type: ignore


class PdmBasicAuth(MultiDomainBasicAuth):
    """A custom auth class that differs from Pip's implementation in the
    following ways:

        - It shows an error message when credentials are not provided or correct.
    """

    def __init__(
        self, prompting: bool = True, index_urls: Optional[List[str]] = None
    ) -> None:
        super().__init__(prompting=True, index_urls=index_urls)
        self._real_prompting = prompting

    def _prompt_for_password(
        self, netloc: str
    ) -> Tuple[Optional[str], Optional[str], bool]:
        if not self._real_prompting:
            raise PdmException(
                f"The credentials for {netloc} are incorrect. "
                "Please run the command with `-v` option."
            )
        return super()._prompt_for_password(netloc)

    def _should_save_password_to_keyring(self) -> bool:
        if keyring is None:
            click.secho(
                "The provided credentials will not be saved into your system.\n"
                "You can enable this by installing keyring:\n"
                "    pipx inject pdm keyring\n"
                "or: pip install --user keyring",
                err=True,
                fg="yellow",
            )
        return super()._should_save_password_to_keyring()


def make_basic_auth(sources: List[Source], prompting: bool) -> PdmBasicAuth:
    return PdmBasicAuth(prompting, [source["url"] for source in sources])
