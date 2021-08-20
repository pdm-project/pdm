import os
from typing import Any, Mapping, Optional

from pep517.wrappers import HookMissing

from pdm.builders.base import EnvBuilder


class EditableBuilder(EnvBuilder):
    """Build egg-info in isolated env with managed Python."""

    FALLBACK_BACKEND = {
        "build-backend": "setuptools_pep660",
        "requires": ["setuptools_pep660"],
    }

    def prepare_metadata(
        self, out_dir: str, config_settings: Optional[Mapping[str, Any]] = None
    ) -> str:
        self.install(self._requires, shared=True)
        try:
            requires = self._hook.get_requires_for_build_editable(config_settings)
            self.install(requires)
            filename = self._hook.prepare_metadata_for_build_editable(
                out_dir, config_settings
            )
        except HookMissing:
            self.init_build_system(self.FALLBACK_BACKEND)
            self.ensure_setup_py()
            return self.prepare_metadata(out_dir, config_settings)
        return os.path.join(out_dir, filename)

    def build(
        self,
        out_dir: str,
        config_settings: Optional[Mapping[str, Any]] = None,
        metadata_directory: Optional[str] = None,
    ) -> str:
        self.install(self._requires, shared=True)
        try:
            requires = self._hook.get_requires_for_build_editable(config_settings)
            self.install(requires)
            filename = self._hook.build_editable(
                out_dir, config_settings, metadata_directory
            )
        except HookMissing:
            self.init_build_system(self.FALLBACK_BACKEND)
            self.ensure_setup_py()
            return self.build(out_dir, config_settings, metadata_directory)
        return os.path.join(out_dir, filename)

    def ensure_setup_py(self) -> str:
        from pdm.pep517.base import Builder
        from pdm.project.metadata import MutableMetadata

        builder = Builder(self.src_dir)
        if os.path.exists(os.path.join(self.src_dir, "pyproject.toml")):
            try:
                builder._meta = MutableMetadata(
                    os.path.join(self.src_dir, "pyproject.toml")
                )
            except ValueError:
                builder._meta = None
        return builder.ensure_setup_py().as_posix()
