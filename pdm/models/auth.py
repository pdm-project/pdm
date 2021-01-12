from typing import List, Optional, Tuple

from pdm._types import Source
from pdm.exceptions import PdmException
from pdm.models.pip_shims import MultiDomainBasicAuth
from pdm.utils import expand_env_vars


class PdmBasicAuth(MultiDomainBasicAuth):
    """A custom auth class that differs from Pip's implementation in the
    following ways:

        1. It expands env variables in URL auth.
        2. It shows an error message when credentials are not provided or correect.
    """

    def _get_url_and_credentials(
        self, original_url: str
    ) -> Tuple[str, Optional[str], Optional[str]]:
        url, username, password = super()._get_url_and_credentials(original_url)

        if username:
            username = expand_env_vars(username)

        if password:
            password = expand_env_vars(password)

        return url, username, password

    def handle_401(self, resp, **kwargs):
        if resp.status_code == 401 and not self.prompting:
            raise PdmException(
                f"The credentials for {resp.request.url} are not provided or correct. "
                "Please run the command with `-v` option."
            )
        return super().handle_401(resp, **kwargs)


def make_basic_auth(sources: List[Source], prompting: bool) -> PdmBasicAuth:
    return PdmBasicAuth(prompting, [source["url"] for source in sources])
