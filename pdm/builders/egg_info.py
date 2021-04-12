import os

from pdm.builders.base import EnvBuilder
from pdm.exceptions import BuildError

_SETUPTOOLS_SHIM = (
    "import sys, setuptools, tokenize; sys.argv[0] = {0!r}; __file__={0!r};"
    "f=getattr(tokenize, 'open', open)(__file__);"
    "code=f.read().replace('\\r\\n', '\\n');"
    "f.close();"
    "exec(compile(code, __file__, 'exec'))"
)


class EnvEggInfoBuilder(EnvBuilder):
    """Build egg-info in isolated env with managed Python."""

    @staticmethod
    def _find_egg_info(directory: str) -> str:
        filename = next(
            (f for f in os.listdir(directory) if f.endswith(".egg-info")),
            None,
        )
        if not filename:
            raise BuildError("No egg info is generated.")
        return filename

    def build(self, out_dir: str) -> str:
        from pdm.pep517.base import Builder
        from pdm.project.metadata import MutableMetadata

        builder = Builder(self.src_dir)
        if os.path.exists(os.path.join(self.src_dir, "pyproject.toml")):
            builder._meta = MutableMetadata(
                os.path.join(self.src_dir, "pyproject.toml")
            )
        setup_py_path = builder.ensure_setup_py().as_posix()
        self.install(["setuptools"])
        args = [self.executable, "-c", _SETUPTOOLS_SHIM.format(setup_py_path)]
        args.extend(["egg_info", "--egg-base", os.path.relpath(out_dir, self.src_dir)])
        self.subprocess_runner(args, cwd=self.src_dir)
        filename = self._find_egg_info(out_dir)
        return os.path.join(out_dir, filename)
