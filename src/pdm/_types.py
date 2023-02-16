from __future__ import annotations

from typing import Any, Dict, List, NamedTuple, Tuple, TypeVar, Union

from pdm.compat import Literal, Protocol, TypedDict


class Source(TypedDict, total=False):
    url: str
    verify_ssl: bool
    name: str
    type: Literal["index", "find_links"]  # noqa: F821
    username: str
    password: str


RequirementDict = Union[str, Dict[str, Union[str, bool]]]
CandidateInfo = Tuple[List[str], str, str]


class Package(NamedTuple):
    name: str
    version: str
    summary: str


class Comparable(Protocol):
    def __lt__(self, __other: Any) -> bool:
        ...


SpinnerT = TypeVar("SpinnerT", bound="Spinner")


class Spinner(Protocol):
    def update(self, text: str) -> None:
        ...

    def __enter__(self: SpinnerT) -> SpinnerT:
        ...

    def __exit__(self, *args: Any) -> None:
        ...


class RichProtocol(Protocol):
    def __rich__(self) -> str:
        ...


SearchResult = List[Package]
