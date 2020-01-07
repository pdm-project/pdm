from pdm.models.repositories import PyPIRepository
from pdm.models.requirements import Requirement
from pdm.models.candidates import Candidate
from pdm.context import context


class FakeProject:
    config = {"cache_dir": "./caches"}
    packages_root = None


context.init(FakeProject())
req = Requirement.from_line("-e ./tests/fixtures/projects/demo")
repo = PyPIRepository([])
can = Candidate(req, repo)
can.prepare_source()
deps = can.get_dependencies_from_metadata()
print(deps)
