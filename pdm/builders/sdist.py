import os

from pdm.builders.base import EnvBuilder


class EnvSdistBuilder(EnvBuilder):
    """Build sdist in isolated env with managed Python."""

    def build(self, out_dir: str) -> str:
        self.install(self._build_system["requires"])
        requires = self._hook.get_requires_for_build_sdist()
        self.install(requires)
        filename = self._hook.build_sdist(out_dir)
        return os.path.join(out_dir, filename)
