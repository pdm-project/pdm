from __future__ import annotations

import os

from pdm.builders.base import EnvBuilder


class SdistBuilder(EnvBuilder):
    """Build sdist in isolated env with managed Python."""

    def build(self, out_dir: str, metadata_directory: str | None = None) -> str:
        self.install(self._requires, shared=True)
        requires = self._hook.get_requires_for_build_sdist(self.config_settings)
        self.install(requires)
        filename = self._hook.build_sdist(out_dir, self.config_settings)
        return os.path.join(out_dir, filename)
