from pdm.formats import flit, legacy, pipfile, poetry, requirements

FORMATS = {
    "pipfile": pipfile,
    "poetry": poetry,
    "flit": flit,
    "requirements": requirements,
    "legacy": legacy,
}
