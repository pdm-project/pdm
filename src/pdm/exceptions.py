from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pdm.models.candidates import Candidate


class PdmException(Exception):
    pass


class ResolutionError(PdmException):
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
        message = f"No metadata information is available for [success]{candidate!s}[/]."
        self.candidate = candidate
        super().__init__(message)


class PDMWarning(Warning):
    pass


class PackageWarning(PDMWarning):
    pass


class PDMDeprecationWarning(PDMWarning, DeprecationWarning):
    pass


warnings.simplefilter("default", category=PDMDeprecationWarning)


class ProjectError(PdmUsageError):
    pass


class InstallationError(PdmException):
    pass


class UninstallError(PdmException):
    pass


class NoConfigError(PdmUsageError, KeyError):
    def __str__(self) -> str:
        return f"No such config key: {self.args[0]!r}"


class NoPythonVersion(PdmUsageError):
    pass


class BuildError(PdmException, RuntimeError):
    pass
