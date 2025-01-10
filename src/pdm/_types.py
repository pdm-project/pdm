from __future__ import annotations

import dataclasses as dc
import re
from typing import TYPE_CHECKING, Any, NamedTuple, TypeVar, Union

if TYPE_CHECKING:
    from typing import Protocol


def _normalize_pattern(pattern: str) -> str:
    return re.sub(r"[^A-Za-z0-9?*\[\]-]+", "-", pattern).lower()


@dc.dataclass
class RepositoryConfig:
    """Private dataclass to be subclassed"""

    config_prefix: str
    name: str

    url: str | None = None
    username: str | None = None
    password: str | None = dc.field(default=None, repr=False)
    verify_ssl: bool | None = None
    type: str | None = None
    ca_certs: str | None = None
    client_cert: str | None = None
    client_key: str | None = None
    include_packages: list[str] = dc.field(default_factory=list)
    exclude_packages: list[str] = dc.field(default_factory=list)

    def __post_init__(self) -> None:
        self.include_packages = [_normalize_pattern(p) for p in self.include_packages]
        self.exclude_packages = [_normalize_pattern(p) for p in self.exclude_packages]

    def populate_keyring_auth(self) -> None:
        if self.username is None or self.password is None:
            from pdm.models.auth import keyring

            service = f"pdm-{self.config_prefix}-{self.name}"
            auth = keyring.get_auth_info(service, self.username)
            if auth is not None:
                self.username, self.password = auth

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
        config_prefix = f"{self.config_prefix}.{self.name}." if self.name else f"{self.config_prefix}."
        lines: list[str] = []
        self.populate_keyring_auth()
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


RequirementDict = Union[str, dict[str, Union[str, bool]]]
CandidateInfo = tuple[list[str], str, str]


class SearchResult(NamedTuple):
    name: str
    version: str
    summary: str


SearchResults = list[SearchResult]


if TYPE_CHECKING:
    from typing import Required, TypedDict

    class Comparable(Protocol):
        def __lt__(self, __other: Any) -> bool: ...

    SpinnerT = TypeVar("SpinnerT", bound="Spinner")

    class Spinner(Protocol):
        def update(self, text: str) -> None: ...

        def __enter__(self: SpinnerT) -> SpinnerT: ...

        def __exit__(self, *args: Any) -> None: ...

    class RichProtocol(Protocol):
        def __rich__(self) -> str: ...

    class FileHash(TypedDict, total=False):
        url: str
        hash: Required[str]
        file: str


class NotSetType:
    pass


NotSet = NotSetType()
