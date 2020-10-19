import logging
import os
import subprocess
import sys
import tempfile
from typing import Iterable

from build import ProjectBuilder
from build.env import IsolatedEnvironment as _Environment
from pep517.wrappers import LoggerWrapper

from pdm.exceptions import BuildError
from pdm.iostream import stream
from pdm.pep517.base import Builder

_SETUPTOOLS_SHIM = (
    "import sys, setuptools, tokenize; sys.argv[0] = {0!r}; __file__={0!r};"
    "f=getattr(tokenize, 'open', open)(__file__);"
    "code=f.read().replace('\\r\\n', '\\n');"
    "f.close();"
    "exec(compile(code, __file__, 'exec'))"
)


class IsolatedEnvironment(_Environment):
    """A subclass of ``build.env.IsolatedEnvironment`` to provide rich output for PDM"""

    def __enter__(self) -> "IsolatedEnvironment":
        inst = super().__enter__()
        # Setting PYTHONHOME will cause encoding initialization error in threads.
        os.environ.pop("PYTHONHOME", None)
        return inst

    def install(self, requirements: Iterable[str]) -> None:
        if not requirements:
            return
        stream.logger.debug("Preparing isolated env for PEP 517 build...")
        log_subprocessor([sys.executable, "-m", "ensurepip"], cwd=self.path)

        with tempfile.NamedTemporaryFile(
            "w+", prefix="build-reqs-", suffix=".txt", delete=False
        ) as req_file:
            req_file.write(os.linesep.join(requirements))
            req_file.close()
            cmd = [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--prefix",
                self.path,
                "-r",
                os.path.abspath(req_file.name),
            ]
            log_subprocessor(cmd)
            os.unlink(req_file.name)


def log_subprocessor(cmd, cwd=None, extra_environ=None):
    env = os.environ.copy()
    if extra_environ:
        env.update(extra_environ)
    try:
        subprocess.check_call(
            cmd,
            cwd=cwd,
            env=env,
            stdout=LoggerWrapper(stream.logger, logging.DEBUG),
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError:
        raise BuildError(f"Call command {cmd} return non-zero status.")


def build_wheel(src_dir: str, out_dir: str) -> str:
    """Build wheel and return the full path of the artifact."""
    builder = ProjectBuilder(srcdir=src_dir)
    with IsolatedEnvironment.for_current() as env, builder.hook.subprocess_runner(
        log_subprocessor
    ):
        env.install(builder.build_dependencies)
        filename = builder.hook.build_wheel(out_dir)
    return os.path.join(out_dir, filename)


def build_sdist(src_dir: str, out_dir: str) -> str:
    """Build sdist and return the full path of the artifact."""
    builder = ProjectBuilder(srcdir=src_dir)
    with IsolatedEnvironment.for_current() as env, builder.hook.subprocess_runner(
        log_subprocessor
    ):
        env.install(builder.build_dependencies)
        filename = builder.hook.build_sdist(out_dir)
    return os.path.join(out_dir, filename)


def _find_egg_info(directory: str) -> str:
    filename = next(
        (f for f in os.listdir(directory) if f.endswith(".egg-info")),
        None,
    )
    if not filename:
        raise BuildError("No egg info is generated.")
    return filename


def build_egg_info(src_dir: str, out_dir: str) -> str:
    # Ignore destination since editable builds should be build locally
    builder = Builder(src_dir)
    setup_py_path = builder.ensure_setup_py().as_posix()
    with IsolatedEnvironment.for_current() as env:
        env.install(["setuptools"])
        args = [sys.executable, "-c", _SETUPTOOLS_SHIM.format(setup_py_path)]
        args.extend(["egg_info", "--egg-base", out_dir])
        log_subprocessor(args, cwd=src_dir)
        filename = _find_egg_info(out_dir)
    return os.path.join(out_dir, filename)
