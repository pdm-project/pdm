class PdmException(Exception):
    pass


class RequirementError(PdmException, ValueError):
    pass


class InvalidPyVersion(PdmException, ValueError):
    pass


class WheelBuildError(PdmException):
    pass


class ProjectNotInitialized(PdmException):
    pass


class CorruptedCacheError(PdmException):
    pass


class CandidateInfoNotFound(PdmException):
    def __init__(self, candidate):
        super().__init__()
        self.candidate = candidate

    def __str__(self):
        return f'No metadata information is available for {self.candidate}'


class ExtrasError(UserWarning):
    def __init__(self, extras):
        super().__init__()
        self.extras = tuple(extras)

    def __str__(self):
        return f"Extras not found: {self.extras}"
