import sys
from typing import Dict, List, NamedTuple, Tuple, Union

if sys.version_info < (3, 8):
    from typing_extensions import Literal  # noqa: F401
else:
    from typing import Literal  # noqa: F401

Source = Dict[str, Union[str, bool]]
RequirementDict = Union[str, Dict[str, Union[bool, str]]]
CandidateInfo = Tuple[List[str], str, str]


class Package(NamedTuple):
    name: str
    version: str
    summary: str


SearchResult = List[Package]
