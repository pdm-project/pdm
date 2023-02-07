from __future__ import annotations

import dataclasses
from typing import Any, Dict, List, NamedTuple, Tuple, TypeVar, Union

from pdm.compat import Protocol


@dataclasses.dataclass
class RepositoryConfig:
    url: str | None = None
    username: str | None = None
    password: str | None = None
    verify_ssl: bool | None = None
    type: str | None = None
    ca_certs: str | None = None

    config_prefix: str | None = None
    name: str | None = None

    def passive_update(self, other: RepositoryConfig | None = None, **kwargs: Any) -> None:
        """An update method that prefers the existing value over the new one."""
        if other is not None:
            for k in other.__dataclass_fields__:
                v = getattr(other, k)
                if getattr(self, k) is None and v is not None:
                    setattr(self, k, v)
        for k, v in kwargs.items():
            if getattr(self, k) is None and v is not None:
                setattr(self, k, v)

    def __rich__(self) -> str:
        config_prefix = f"{self.config_prefix}." if self.config_prefix is not None else ""
        lines: list[str] = []
        if self.url:
            lines.append(f"[primary]{config_prefix}url[/] = {self.url}")
        if self.username:
            lines.append(f"[primary]{config_prefix}username[/] = {self.username}")
        if self.password:
            lines.append(f"[primary]{config_prefix}password[/] = [i]<hidden>[/]")
        if self.verify_ssl is not None:
            lines.append(f"[primary]{config_prefix}verify_ssl[/] = {self.verify_ssl}")
        if self.type:
            lines.append(f"[primary]{config_prefix}type[/] = {self.type}")
        if self.ca_certs:
            lines.append(f"[primary]{config_prefix}ca_certs[/] = {self.ca_certs}")
        return "\n".join(lines)


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
