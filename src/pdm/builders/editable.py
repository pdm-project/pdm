from __future__ import annotations

import os
from typing import Any, ClassVar

from pyproject_hooks import HookMissing

from pdm.builders.base import EnvBuilder
from pdm.termui import logger


class EditableBuilder(EnvBuilder):
    """Build egg-info in isolated env with managed Python."""

    FALLBACK_BACKEND: ClassVar[dict[str, Any]] = {
        "build-backend": "setuptools_pep660",
        "requires": ["setuptools_pep660"],
    }

    def prepare_metadata(self, out_dir: str) -> str:
        self.install(self._requires, shared=True)
        try:
            requires = self._hook.get_requires_for_build_editable(self.config_settings)
            self.install(requires)
            filename = self._hook.prepare_metadata_for_build_editable(out_dir, self.config_settings)
        except HookMissing:
            self.init_build_system(self.FALLBACK_BACKEND)
            return self.prepare_metadata(out_dir)
        return os.path.join(out_dir, filename)

    def build(self, out_dir: str, metadata_directory: str | None = None) -> str:
        self.install(self._requires, shared=True)
        try:
            requires = self._hook.get_requires_for_build_editable(self.config_settings)
            self.install(requires)
            filename = self._hook.build_editable(out_dir, self.config_settings, metadata_directory)
        except HookMissing:
            logger.warning("The build backend doesn't support PEP 660, falling back to setuptools-pep660")
            self.init_build_system(self.FALLBACK_BACKEND)
            return self.build(out_dir, metadata_directory=metadata_directory)
        return os.path.join(out_dir, filename)
