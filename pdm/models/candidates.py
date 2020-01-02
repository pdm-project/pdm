class Candidate:
    """A concrete candidate that can be downloaded and installed."""


class LocalDirCandidate(Candidate):
    pass


class FileCandidate(Candidate):
    pass


class VcsCandidate(LocalDirCandidate):
    pass
