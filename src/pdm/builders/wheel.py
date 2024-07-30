from __future__ import annotations

import os

from pdm.builders.base import EnvBuilder, wrap_error


class WheelBuilder(EnvBuilder):
    """Build wheel in isolated env with managed Python."""

    @wrap_error
    def prepare_metadata(self, out_dir: str) -> str:
        if self.isolated:
            self.install(self._requires, shared=True)
            requires = self._hook.get_requires_for_build_wheel(self.config_settings)
            self.install(requires)
        filename = self._hook.prepare_metadata_for_build_wheel(out_dir, self.config_settings)
        return os.path.join(out_dir, filename)

    @wrap_error
    def build(self, out_dir: str, metadata_directory: str | None = None) -> str:
        if self.isolated:
            self.install(self._requires, shared=True)
            requires = self._hook.get_requires_for_build_wheel(self.config_settings)
            self.install(requires)
        filename = self._hook.build_wheel(out_dir, self.config_settings, metadata_directory)
        return os.path.join(out_dir, filename)
