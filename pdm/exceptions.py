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
        return f"No metadata information is available for {self.candidate}"


class ExtrasError(UserWarning):
    def __init__(self, extras):
        super().__init__()
        self.extras = tuple(extras)

    def __str__(self):
        return f"Extras not found: {self.extras}"


class ProjectError(PdmException):
    pass


class NoConfigError(PdmException, KeyError):
    pass


class ResolutionError(PdmException):
    pass


class ResolutionImpossible(ResolutionError):
    def __init__(self, requirements):
        super(ResolutionImpossible, self).__init__()
        self.requirements = requirements


class ResolutionTooDeep(ResolutionError):
    def __init__(self, round_count):
        super(ResolutionTooDeep, self).__init__(round_count)
        self.round_count = round_count


class NoVersionsAvailable(ResolutionError):
    def __init__(self, requirement, parent):
        super(NoVersionsAvailable, self).__init__()
        self.requirement = requirement
        self.parent = parent


class RequirementsConflicted(ResolutionError):
    def __init__(self, requirements):
        super(RequirementsConflicted, self).__init__()
        self.requirements = requirements


class NoPythonVersion(PdmException):
    pass


class CommandNotFound(PdmException):
    def __init__(self, command):
        super.__init__(command)
        self.command = command

    def __str__(self):
        return f"'{self.command}' is not found in your PATH."
