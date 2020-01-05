class PdmException(Exception):
    pass


class RequirementError(PdmException, ValueError):
    pass


class InvalidPyVersion(PdmException, ValueError):
    pass
