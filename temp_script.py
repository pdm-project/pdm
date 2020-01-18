import logging

from pdm.installers import Installer
from pdm.project import Project

project = Project()
installer = Installer(project.environment)

can = project.get_locked_candidates()['pythonfinder']
installer.install(can)
