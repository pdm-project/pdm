from __future__ import annotations

import os

from pdm.builders.base import EnvBuilder, wrap_error
from pdm.termui import logger


class SdistBuilder(EnvBuilder):
    """Build sdist in isolated env with managed Python."""

    @wrap_error
    def build(self, out_dir: str, metadata_directory: str | None = None) -> str:
        if self.isolated:
            self.install(self._requires, shared=True)
            requires = self._hook.get_requires_for_build_sdist(self.config_settings)
            self.install(requires)
        lib = self._env.get_paths()["purelib"]
        logger.info("Libs(%s): %s", lib, os.listdir(lib))
        logger.info("PYTHONPATH: %s", self._env_vars["PYTHONPATH"])
        filename = self._hook.build_sdist(out_dir, self.config_settings)
        return os.path.join(out_dir, filename)
