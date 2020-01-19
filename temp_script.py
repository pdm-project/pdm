import tomlkit
from pdm.cli import actions
from pdm.models.requirements import parse_requirement
from pdm.project import Project

req = parse_requirement("git+https://github.com/test-root/demo.git#egg=demo", True)
project = Project()
actions.do_lock(project)
