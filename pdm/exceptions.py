from __future__ import annotations

from typing import TYPE_CHECKING, List

from pdm import termui

if TYPE_CHECKING:
    from pdm.models.candidates import Candidate


class PdmError(Exception):
    pass


class PdmUsageError(PdmError):
    pass


class RequirementError(PdmError, ValueError):
    pass


class InvalidPyVersionError(PdmError, ValueError):
    pass


class CorruptedCacheError(PdmError):
    pass


class CandidateNotFoundError(PdmError):
    pass


class CandidateInfoNotFoundError(PdmError):
    def __init__(self, candidate: Candidate) -> None:
        message = (
            "No metadata information is available for "
            f"{termui.green(str(candidate))}."
        )
        self.candidate = candidate
        super().__init__(message)


class ExtrasError(UserWarning):
    def __init__(self, extras: List[str]) -> None:
        super().__init__()
        self.extras = tuple(extras)

    def __str__(self) -> str:
        return f"Extras not found: {self.extras}"


class ProjectError(PdmUsageError):
    pass


class InstallationError(PdmError):
    pass


class UninstallError(PdmError):
    pass


class NoConfigError(PdmError, KeyError):
    def __init__(self, key: str) -> None:
        super().__init__("No such config item: {}".format(key))


class NoPythonVersionError(PdmError):
    pass


class BuildError(PdmError, RuntimeError):
    pass
