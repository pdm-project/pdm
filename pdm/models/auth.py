from typing import Any, List

from pip._vendor.requests.models import Response

from pdm._types import Source
from pdm.exceptions import PdmException
from pdm.models.pip_shims import MultiDomainBasicAuth


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


def make_basic_auth(sources: List[Source], prompting: bool) -> PdmBasicAuth:
    return PdmBasicAuth(prompting, [source["url"] for source in sources])
