import os
from typing import Any, Mapping, Optional

from pdm.builders.base import EnvBuilder


class EnvWheelBuilder(EnvBuilder):
    """Build wheel in isolated env with managed Python."""

    def build(
        self, out_dir: str, config_settings: Optional[Mapping[str, Any]] = None
    ) -> str:
        self.install(self._build_system["requires"])
        requires = self._hook.get_requires_for_build_wheel(config_settings)
        self.install(requires)
        filename = self._hook.build_wheel(out_dir, config_settings)
        return os.path.join(out_dir, filename)
