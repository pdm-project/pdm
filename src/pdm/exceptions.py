from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pdm.models.candidates import Candidate


class PdmException(Exception):
    pass


class PdmArgumentError(PdmException):
    pass


class PdmUsageError(PdmException):
    pass


class RequirementError(PdmUsageError, ValueError):
    pass


class PublishError(PdmUsageError):
    pass


class InvalidPyVersion(PdmUsageError, ValueError):
    pass


class CandidateNotFound(PdmException):
    pass


class CandidateInfoNotFound(PdmException):
    def __init__(self, candidate: Candidate) -> None:
        message = f"No metadata information is available for [success]{str(candidate)}[/]."
        self.candidate = candidate
        super().__init__(message)


class ExtrasWarning(UserWarning):
    def __init__(self, project_name: str, extras: list[str]) -> None:
        super().__init__(f"Extras not found for {project_name}: [{','.join(extras)}]")
        self.extras = tuple(extras)


class ProjectError(PdmUsageError):
    pass


class InstallationError(PdmException):
    pass


class UninstallError(PdmException):
    pass


class NoConfigError(PdmUsageError, KeyError):
    def __init__(self, key: str) -> None:
        super().__init__(f"No such config item: {key}")


class NoPythonVersion(PdmUsageError):
    pass


class BuildError(PdmException, RuntimeError):
    pass
