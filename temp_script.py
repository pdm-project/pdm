import logging

from pdm.cli.actions import do_add
from pdm.installers import Installer
from pdm.project import Project

project = Project()
do_add(project, False, None, True, "compatible", "reuse", (), ("parver",))
