import logging

from pdm.installers import Installer
from pdm.project import Project

project = Project()
# lock(project)
installer = Installer(project.environment)
installer.uninstall("idna")
