import logging

from pdm.project import Project
from pdm.resolver import lock

project = Project()
data = lock(project)
