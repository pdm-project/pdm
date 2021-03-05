from __future__ import annotations

import os
from typing import TYPE_CHECKING, Dict, Iterable, Protocol, Tuple

from pdm.formats import flit, legacy, pipfile, poetry, requirements, setup_py

if TYPE_CHECKING:
    import argparse

    from pdm.models.candidates import Candidate
    from pdm.project import Project


class FormatConverter(Protocol):
    def check_fingerprint(self, project: Project, filename: os.PathLike) -> bool:
        ...

    def convert(self, project: Project, filename: os.PathLike) -> Tuple[dict, dict]:
        ...

    def export(
        self,
        project: Project,
        candidates: Iterable[Candidate],
        options: argparse.Namespace,
    ) -> str:
        ...


FORMATS: Dict[str, FormatConverter] = {
    "pipfile": pipfile,
    "poetry": poetry,
    "flit": flit,
    "requirements": requirements,
    "legacy": legacy,
    "setuppy": setup_py,
}
