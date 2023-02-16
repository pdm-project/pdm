from __future__ import annotations

import os
from typing import Any, Mapping

from pdm.builders.base import EnvBuilder


class WheelBuilder(EnvBuilder):
    """Build wheel in isolated env with managed Python."""

    def prepare_metadata(self, out_dir: str, config_settings: Mapping[str, Any] | None = None) -> str:
        self.install(self._requires, shared=True)
        requires = self._hook.get_requires_for_build_wheel(config_settings)
        self.install(requires)
        filename = self._hook.prepare_metadata_for_build_wheel(out_dir, config_settings)
        return os.path.join(out_dir, filename)

    def build(
        self,
        out_dir: str,
        config_settings: Mapping[str, Any] | None = None,
        metadata_directory: str | None = None,
    ) -> str:
        self.install(self._requires, shared=True)
        requires = self._hook.get_requires_for_build_wheel(config_settings)
        self.install(requires)
        filename = self._hook.build_wheel(out_dir, config_settings, metadata_directory)
        return os.path.join(out_dir, filename)
