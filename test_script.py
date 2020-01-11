import json

from pdm.context import context
from pdm.models.candidates import Candidate
from pdm.models.repositories import PyPIRepository
from pdm.models.requirements import Requirement
from pdm.models.specifiers import PySpecSet
from pdm.resolver import lock
from resolvelib import Resolver


class FakeProject:
    config = {"cache_dir": "./caches"}
    packages_root = None
    python_requires = PySpecSet(">=3.6")


context.init(FakeProject())

source = {"url": "https://pypi.org/simple", "index": "pypi", "verify_ssl": True}
repo = PyPIRepository([source])

data = lock(["tensorflow"], repo, FakeProject.python_requires, False)
json.dumps(data, indent=2)
