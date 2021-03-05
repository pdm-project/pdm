from __future__ import annotations

from pdm.formats import flit, legacy, pipfile, poetry, requirements, setup_py

FORMATS = {
    "pipfile": pipfile,
    "poetry": poetry,
    "flit": flit,
    "requirements": requirements,
    "legacy": legacy,
    "setuppy": setup_py,
}
