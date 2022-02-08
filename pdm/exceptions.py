from __future__ import annotations

from typing import TYPE_CHECKING, List

from pdm import termui

if TYPE_CHECKING:
    from pdm.models.candidates import Candidate


class PdmException(Exception):
    pass


class PdmUsageError(PdmException):
    pass


class RequirementError(PdmException, ValueError):
    pass


class InvalidPyVersion(PdmException, ValueError):
    pass


class CorruptedCacheError(PdmException):
    pass


class CandidateNotFound(PdmException):
    pass


class CandidateInfoNotFound(PdmException):
    def __init__(self, candidate: Candidate) -> None:
        message = (
            "No metadata information is available for "
            f"{termui.green(str(candidate))}."
        )
        self.candidate = candidate
        super().__init__(message)


class ExtrasWarning(UserWarning):
    def __init__(self, project_name: str, extras: List[str]) -> None:
        super().__init__(f"Extras not found for {project_name}: [{','.join(extras)}]")
        self.extras = tuple(extras)


class ProjectError(PdmUsageError):
    pass


class InstallationError(PdmException):
    pass


class UninstallError(PdmException):
    pass


class NoConfigError(PdmException, KeyError):
    def __init__(self, key: str) -> None:
        super().__init__("No such config item: {}".format(key))


class NoPythonVersion(PdmException):
    pass


class BuildError(PdmException, RuntimeError):
    pass
