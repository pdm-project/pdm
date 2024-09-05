from __future__ import annotations

import dataclasses as dc
import re
from typing import TYPE_CHECKING, Any, Dict, List, NamedTuple, Tuple, TypeVar, Union

if TYPE_CHECKING:
    from typing import Protocol


def _normalize_pattern(pattern: str) -> str:
    return re.sub(r"[^A-Za-z0-9?*\[\]-]+", "-", pattern).lower()


@dc.dataclass
class _RepositoryConfig:
    """Private dataclass to be subclassed"""

    config_prefix: str
    name: str

    url: str | None = None
    username: str | None = None
    _password: str | None = dc.field(default=None, repr=False)
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


class RepositoryConfig(_RepositoryConfig):
    def __init__(self, *args: Any, password: str | None = None, **kwargs: Any) -> None:
        kwargs["_password"] = password
        super().__init__(*args, **kwargs)

    @property
    def password(self) -> str | None:
        if self._password is None:
            from pdm.models.auth import keyring

            service = f"pdm-{self.config_prefix}-{self.name}"
            result = keyring.get_auth_info(service, self.username)
            if result is not None:
                self._password = result[1]
        return self._password

    @password.setter
    def password(self, value: str) -> None:
        self._password = value

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


class SearchResult(NamedTuple):
    name: str
    version: str
    summary: str


SearchResults = List[SearchResult]


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
