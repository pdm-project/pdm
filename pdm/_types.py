import sys
from typing import Any, Dict, List, NamedTuple, Tuple, Union

if sys.version_info >= (3, 8):
    from importlib.metadata import Distribution
    from typing import Literal, Protocol, TypedDict
else:
    from importlib_metadata import Distribution
    from typing_extensions import Literal, Protocol, TypedDict


class Source(TypedDict, total=False):
    url: str
    verify_ssl: bool
    name: str
    type: Union[Literal["index"], Literal["find_links"]]


RequirementDict = Union[str, Dict[str, Union[bool, str]]]
CandidateInfo = Tuple[List[str], str, str]


class Package(NamedTuple):
    name: str
    version: str
    summary: str


class Comparable(Protocol):
    def __lt__(self, __other: Any) -> bool:
        ...


SearchResult = List[Package]

__all__ = (
    "Literal",
    "Source",
    "RequirementDict",
    "CandidateInfo",
    "Distribution",
    "Package",
    "SearchResult",
    "Protocol",
)
