from __future__ import annotations

from argparse import Namespace
from os import PathLike
from typing import Iterable, Mapping, Optional, Tuple, TypeVar, cast

from pdm._types import Protocol
from pdm.formats import flit, legacy, pipfile, poetry, requirements, setup_py
from pdm.models.candidates import Candidate
from pdm.models.requirements import Requirement
from pdm.project import Project

_T = TypeVar("_T", Candidate, Requirement)


class _Format(Protocol):
    def check_fingerprint(self, project: Optional[Project], filename: PathLike) -> bool:
        ...

    def convert(
        self,
        project: Optional[Project],
        filename: PathLike,
        options: Optional[Namespace],
    ) -> Tuple[Mapping, Mapping]:
        ...

    def export(
        self, project: Project, candidates: Iterable[_T], options: Optional[Namespace]
    ) -> str:
        ...


FORMATS: Mapping[str, _Format] = {
    "pipfile": cast(_Format, pipfile),
    "poetry": cast(_Format, poetry),
    "flit": cast(_Format, flit),
    "requirements": cast(_Format, requirements),
    "legacy": cast(_Format, legacy),
    "setuppy": cast(_Format, setup_py),
}
