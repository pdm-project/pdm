from typing import Any, List

import click
from pip._vendor.requests.models import Response

from pdm._types import Source
from pdm.exceptions import PdmException
from pdm.models.pip_shims import MultiDomainBasicAuth

try:
    import keyring
except ModuleNotFoundError:
    keyring = None


class PdmBasicAuth(MultiDomainBasicAuth):
    """A custom auth class that differs from Pip's implementation in the
    following ways:

        - It shows an error message when credentials are not provided or correect.
    """

    def handle_401(self, resp: Response, **kwargs: Any) -> Response:
        if resp.status_code == 401 and not self.prompting:
            raise PdmException(
                f"The credentials for {resp.request.url} are not provided or correct. "
                "Please run the command with `-v` option."
            )
        return super().handle_401(resp, **kwargs)

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
