import sys
from typing import Dict, List, NamedTuple, Tuple, Union

if sys.version_info >= (3, 8):
    from typing import Literal, Protocol, TypedDict
else:
    from typing_extensions import Literal, Protocol, TypedDict


class Source(TypedDict):
    url: str
    verify_ssl: bool
    name: str


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
    "Protocol",
)
