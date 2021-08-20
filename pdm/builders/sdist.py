import os
from typing import Any, Mapping, Optional

from pdm.builders.base import EnvBuilder


class SdistBuilder(EnvBuilder):
    """Build sdist in isolated env with managed Python."""

    def build(
        self,
        out_dir: str,
        config_settings: Optional[Mapping[str, Any]] = None,
        metadata_directory: Optional[str] = None,
    ) -> str:
        self.install(self._requires, shared=True)
        requires = self._hook.get_requires_for_build_sdist(config_settings)
        self.install(requires)
        filename = self._hook.build_sdist(out_dir, config_settings)
        return os.path.join(out_dir, filename)
