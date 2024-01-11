import sys

from pdm import environments
from pdm.utils import deprecation_warning

deprecation_warning(
    "pdm.models.environment is deprecated, please use pdm.environments instead. "
    "This module will be removed in the future.",
    stacklevel=1,
)

sys.modules[__name__] = environments
