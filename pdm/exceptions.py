from typing import List

from pdm import termui


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


class PackageIndexError(PdmException):
    pass


class CandidateInfoNotFound(PdmException):
    def __init__(self, candidate) -> None:
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


class ProjectError(PdmException):
    pass


class InstallationError(PdmException):
    pass


class NoConfigError(PdmException, KeyError):
    def __init__(self, key: str) -> None:
        super().__init__("No such config item: {}".format(key))


class NoPythonVersion(PdmException):
    pass


class BuildError(PdmException, RuntimeError):
    pass
