from __future__ import annotations

import base64
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional

import toml
from pep517.wrappers import Pep517HookCaller

from pdm.exceptions import BuildError
from pdm.models.in_process import get_python_version, get_sys_config_paths
from pdm.pep517.base import Builder
from pdm.termui import logger
from pdm.utils import cached_property

if TYPE_CHECKING:
    from pdm.models.environment import Environment

_SETUPTOOLS_SHIM = (
    "import sys, setuptools, tokenize; sys.argv[0] = {0!r}; __file__={0!r};"
    "f=getattr(tokenize, 'open', open)(__file__);"
    "code=f.read().replace('\\r\\n', '\\n');"
    "f.close();"
    "exec(compile(code, __file__, 'exec'))"
)


class LoggerWrapper(threading.Thread):
    """
    Read messages from a pipe and redirect them
    to a logger (see python's logging module).
    """

    def __init__(self, logger: Logger, level: int) -> None:
        super().__init__()
        self.daemon = True

        self.logger = logger
        self.level = level

        # create the pipe and reader
        self.fd_read, self.fd_write = os.pipe()
        self.reader = os.fdopen(self.fd_read)
        # A sentinel random string as stop sign
        self._stop_bit = base64.b85encode(os.urandom(16)).decode()

        self.start()

    def fileno(self) -> int:
        return self.fd_write

    @staticmethod
    def remove_newline(msg: str) -> str:
        return msg[:-1] if msg.endswith("\n") else msg

    def run(self) -> None:
        for line in self.reader:
            if line == self._stop_bit:
                os.close(self.fd_read)
                break
            self._write(self.remove_newline(line))

    def _write(self, message: str) -> None:
        self.logger.log(self.level, message)

    def stop(self) -> None:
        with os.fdopen(self.fd_write, "w") as f:
            f.write(self._stop_bit)
        self.join()


def log_subprocessor(
    cmd: List[str],
    cwd: Optional[os.PathLike] = None,
    extra_environ: Optional[Dict[str, str]] = None,
):
    env = os.environ.copy()
    if extra_environ:
        env.update(extra_environ)
    outstream = LoggerWrapper(logger, logging.DEBUG)
    try:
        subprocess.check_call(
            cmd,
            cwd=cwd,
            env=env,
            stdout=outstream,
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError:
        raise BuildError(f"Call command {cmd} return non-zero status.")
    finally:
        outstream.stop()


def _find_egg_info(directory: str) -> str:
    filename = next(
        (f for f in os.listdir(directory) if f.endswith(".egg-info")),
        None,
    )
    if not filename:
        raise BuildError("No egg info is generated.")
    return filename


class EnvBuilder:
    """A simple PEP 517 builder for an isolated environment"""

    DEFAULT_BACKEND = {
        "build-backend": "setuptools.build_meta:__legacy__",
        "requires": ["setuptools >= 40.8.0", "wheel"],
    }

    def __init__(self, src_dir: os.PathLike, environment: Environment) -> None:
        self._env = environment
        self._path: Optional[str] = None
        self._saved_env = None
        self.executable = self._env.python_executable
        self.src_dir = src_dir

        try:
            with open(os.path.join(src_dir, "pyproject.toml"), encoding="utf8") as f:
                spec = toml.load(f)
        except FileNotFoundError:
            spec = {}
        except Exception as e:
            raise BuildError(e) from e
        self._build_system = spec.get("build-system", self.DEFAULT_BACKEND)

        if "build-backend" not in self._build_system:
            self._build_system["build-backend"] = self.DEFAULT_BACKEND["build-backend"]

        if "requires" not in self._build_system:
            raise BuildError("Missing 'build-system.requires' in pyproject.toml")

        self._backend = self._build_system["build-backend"]

        self._hook = Pep517HookCaller(
            src_dir,
            self._backend,
            backend_path=self._build_system.get("backend-path"),
            runner=self.subprocess_runner,
            python_executable=self.executable,
        )

    @cached_property
    def pip_command(self) -> List[str]:
        return self._get_pip_command()

    def subprocess_runner(
        self,
        cmd: List[str],
        cwd: Optional[str] = None,
        extra_environ: Optional[Dict[str, str]] = None,
    ) -> Optional[Any]:
        env = self._saved_env.copy() if self._saved_env else {}
        if extra_environ:
            env.update(extra_environ)
        return log_subprocessor(cmd, cwd, extra_environ=env)

    def _download_pip_wheel(self, path: os.PathLike):
        dirname = Path(tempfile.mkdtemp(prefix="pip-download-"))
        try:
            self.subprocess_runner(
                [
                    getattr(sys, "_original_executable", sys.executable),
                    "-m",
                    "pip",
                    "download",
                    "--only-binary=:all:",
                    "-d",
                    dirname,
                    "pip<21",  # pip>=21 drops the support of py27
                ]
            )
            wheel_file = next(dirname.glob("pip-*.whl"))
            shutil.move(str(wheel_file), path)
        finally:
            shutil.rmtree(dirname, ignore_errors=True)

    def _get_pip_command(self) -> List[str]:
        """Get a pip command that has pip installed.
        E.g: ['python', '-m', 'pip']
        """
        python_version, _ = get_python_version(self.executable)
        proc = subprocess.run(
            [self.executable, "-Im", "pip", "--version"], capture_output=True
        )
        if proc.returncode == 0:
            # The pip has already been installed with the executable, just use it
            return [self.executable, "-Im", "pip"]
        if python_version[0] == 3:
            # Use the ensurepip to provision one.
            try:
                self.subprocess_runner(
                    [self.executable, "-Im", "ensurepip", "--upgrade", "--default-pip"]
                )
            except BuildError:
                pass
            else:
                return [self.executable, "-Im", "pip"]
        # Otherwise, download a pip wheel from the Internet.
        pip_wheel = self._env.project.cache_dir / "pip.whl"
        if not pip_wheel.is_file():
            self._download_pip_wheel(pip_wheel)
        return [self.executable, str(pip_wheel / "pip")]

    def __enter__(self) -> EnvBuilder:
        self._path = tempfile.mkdtemp(prefix="pdm-build-env-")
        paths = get_sys_config_paths(
            self.executable, vars={"base": self._path, "platbase": self._path}
        )
        old_path = os.getenv("PATH")
        self._saved_env = {
            "PYTHONPATH": paths["purelib"],
            "PATH": paths["scripts"]
            if not old_path
            else os.pathsep.join([paths["scripts"], old_path]),
            "PYTHONNOUSERSITE": "1",
            "PDM_PYTHON_PEP582": "0",
        }
        logger.debug("Preparing isolated env for PEP 517 build...")
        return self

    def __exit__(self, *args: Any) -> None:
        self._saved_env = None
        shutil.rmtree(self._path, ignore_errors=True)

    def install(self, requirements: Iterable[str]) -> None:
        if not requirements:
            return

        with tempfile.NamedTemporaryFile(
            "w+", prefix="pdm-build-reqs-", suffix=".txt", delete=False
        ) as req_file:
            req_file.write(os.linesep.join(requirements))
            req_file.close()
            cmd = self.pip_command + [
                "install",
                "--prefix",
                self._path,
                "-r",
                os.path.abspath(req_file.name),
            ]
            self.subprocess_runner(cmd)
            os.unlink(req_file.name)

    def build_wheel(self, out_dir: str) -> str:
        """Build wheel and return the full path of the artifact."""
        self.install(self._build_system["requires"])
        requires = self._hook.get_requires_for_build_wheel()
        self.install(requires)
        filename = self._hook.build_wheel(out_dir)
        return os.path.join(out_dir, filename)

    def build_sdist(self, out_dir: str) -> str:
        """Build sdist and return the full path of the artifact."""
        self.install(self._build_system["requires"])
        requires = self._hook.get_requires_for_build_sdist()
        self.install(requires)
        filename = self._hook.build_sdist(out_dir)
        return os.path.join(out_dir, filename)

    def build_egg_info(self, out_dir: str) -> str:
        # Ignore destination since editable builds should be build locally
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
        filename = _find_egg_info(out_dir)
        return os.path.join(out_dir, filename)
