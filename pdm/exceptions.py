from pdm.iostream import stream


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


class NoPythonVersion(PdmException):
    pass


class BuildError(PdmException, RuntimeError):
    pass
