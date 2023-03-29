import sys
import warnings

from pdm import environments

warnings.warn(
    "pdm.models.environment is deprecated, please use pdm.environments instead. "
    "This module will be removed in the future.",
    DeprecationWarning,
    stacklevel=1,
)

sys.modules[__name__] = environments
