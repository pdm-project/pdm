from pdm.iostream import stream


class PdmException(Exception):
    pass


class PdmUsageError(PdmException):
    pass


class RequirementError(PdmException, ValueError):
    pass


class InvalidPyVersion(PdmException, ValueError):
    pass


class WheelBuildError(PdmException):
    pass


class CorruptedCacheError(PdmException):
    pass


class CandidateInfoNotFound(PdmException):
    def __init__(self, candidate):
        message = (
            "No metadata information is available for "
            f"{stream.green(str(candidate))}."
        )
        self.candidate = candidate
        super().__init__(message)


class ExtrasError(UserWarning):
    def __init__(self, extras):
        super().__init__()
        self.extras = tuple(extras)

    def __str__(self):
        return f"Extras not found: {self.extras}"


class ProjectError(PdmException):
    pass


class InstallationError(PdmException):
    pass


class NoConfigError(PdmException, KeyError):
    def __init__(self, key):
        super().__init__("No such config item: {}".format(key))


class ResolutionError(PdmException):
    pass


class ResolutionImpossible(ResolutionError):
    def __init__(self, requirements):
        super().__init__("Resolution impossible")
        self.requirements = requirements


class ResolutionTooDeep(ResolutionError):
    def __init__(self, round_count):
        super().__init__(round_count)
        self.round_count = round_count


class NoVersionsAvailable(ResolutionError):
    def __init__(self, requirement, parent):
        super().__init__(
            "No version available for {}.".format(stream.green(requirement.as_line()))
        )
        self.requirement = requirement
        self.parent = parent


class RequirementsConflicted(ResolutionError):
    def __init__(self, requirements):
        super(RequirementsConflicted, self).__init__("Requirements conflicted")
        self.requirements = requirements


class NoPythonVersion(PdmException):
    pass
