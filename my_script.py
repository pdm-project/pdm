from pdm.models.repositories import PyPIRepository
from pdm.models.requirements import Requirement
from pdm.models.candidates import Candidate
from pdm.models.specifiers import PySpecSet
from pdm.context import context
from resolvelib import Resolver
from pdm.resolver import lock


class FakeProject:
    config = {"cache_dir": "./caches"}
    packages_root = None
    python_requires = PySpecSet(">=3.6")


context.init(FakeProject())

source = {"url": "https://pypi.org/simple", "index": "pypi", "verify_ssl": True}
repo = PyPIRepository([source])

state = lock(['pytest'], repo, FakeProject.python_requires, False)
for k, v in state.mapping.items():
    print(v, v.marker)
print(state.mapping['pytest'].hashes)
