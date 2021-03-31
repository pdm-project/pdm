import sys
from typing import Dict, List, NamedTuple, Tuple, Union

if sys.version_info >= (3, 8):
    from typing import Literal
else:
    from typing_extensions import Literal

Source = Dict[str, Union[str, bool]]
RequirementDict = Union[str, Dict[str, Union[bool, str]]]
CandidateInfo = Tuple[List[str], str, str]


class Package(NamedTuple):
    name: str
    version: str
    summary: str


SearchResult = List[Package]

__all__ = (
    "Literal",
    "Source",
    "RequirementDict",
    "CandidateInfo",
    "Package",
    "SearchResult",
)
