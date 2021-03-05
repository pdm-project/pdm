import os


def check_fingerprint(project, filename):
    return os.path.basename(filename) == "setup.py"


def convert(project, filename):
    raise NotImplementedError()


def export(project, candidates, options):
    from pdm.pep517.base import Builder

    builder = Builder(project.root)
    return builder.format_setup_py()
