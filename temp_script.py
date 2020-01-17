import logging

from pdm.project import Project
from pdm.resolver import lock

project = Project()
# lock(project)
installer = project.get_installer()
for can in project.get_locked_candidates():
    installer.install_candidate(can)
