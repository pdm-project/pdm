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
