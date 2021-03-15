from typing import Dict, List, NamedTuple, Tuple, Union

try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal  # noqa

Source = Dict[str, Union[str, bool]]
RequirementDict = Union[str, Dict[str, Union[bool, str]]]
CandidateInfo = Tuple[List[str], str, str]


class Package(NamedTuple):
    name: str
    version: str
    summary: str


SearchResult = List[Package]
