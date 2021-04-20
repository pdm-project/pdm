from __future__ import annotations

import base64
import logging
import os
import subprocess
import tempfile
import textwrap
import threading
from logging import Logger
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional

import toml
from pep517.wrappers import Pep517HookCaller
from pip._vendor.pkg_resources import Requirement, VersionConflict, WorkingSet

from pdm.exceptions import BuildError
from pdm.models.in_process import get_sys_config_paths
from pdm.termui import logger
from pdm.utils import create_tracked_tempdir, prepare_pip_source_args

if TYPE_CHECKING:
    from pdm.models.environment import Environment


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
) -> None:
    env = os.environ.copy()
    if extra_environ:
        env.update(extra_environ)
    outstream = LoggerWrapper(logger, logging.DEBUG)
    try:
        subprocess.check_call(
            cmd,
            cwd=cwd,
            env=env,
            stdout=outstream.fileno(),
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError:
        raise BuildError(f"Call command {cmd} return non-zero status.")
    finally:
        outstream.stop()


class _Prefix:
    def __init__(self, executable: str, path: str) -> None:
        self.path = path
        paths = get_sys_config_paths(executable, vars={"base": path, "platbase": path})
        self.bin_dir = paths["scripts"]
        self.lib_dirs = [paths["platlib"], paths["purelib"]]
        self.site_dir = os.path.join(path, "site")
        if not os.path.isdir(self.site_dir):
            os.makedirs(self.site_dir)
        with open(os.path.join(self.site_dir, "sitecustomize.py"), "w") as fp:
            fp.write(
                textwrap.dedent(
                    """
                import sys, os, site

                original_sys_path = sys.path[:]
                known_paths = set()
                site.addusersitepackages(known_paths)
                site.addsitepackages(known_paths)
                known_paths = {{os.path.normpath(p) for p in known_paths}}
                original_sys_path = [
                    p for p in original_sys_path
                    if os.path.normpath(p) not in known_paths]
                sys.path[:] = original_sys_path
                for lib_path in {lib_paths!r}:
                    site.addsitedir(lib_path)
                """.format(
                        lib_paths=self.lib_dirs
                    )
                )
            )


class EnvBuilder:
    """A simple PEP 517 builder for an isolated environment"""

    _env_cache: Dict[str, str] = {}

    DEFAULT_BACKEND = {
        "build-backend": "setuptools.build_meta:__legacy__",
        "requires": ["setuptools >= 40.8.0", "wheel"],
    }

    @classmethod
    def get_env_path(cls, src_dir: os.PathLike) -> str:
        key = os.path.normpath(src_dir).rstrip("\\/")
        if key not in cls._env_cache:
            cls._env_cache[key] = create_tracked_tempdir(prefix="pdm-build-env-")
        return cls._env_cache[key]

    def __init__(self, src_dir: os.PathLike, environment: Environment) -> None:
        self._env = environment
        self._path = self.get_env_path(src_dir)
        self.executable = self._env.interpreter.executable
        self.src_dir = src_dir
        self._prefix = _Prefix(self.executable, self._path)
        logger.debug("Preparing isolated env for PEP 517 build...")
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

    @property
    def _env_vars(self) -> Dict[str, str]:
        paths = [self._prefix.bin_dir]
        if "PATH" in os.environ:
            paths.append(os.getenv("PATH", ""))
        return {
            "PYTHONPATH": self._prefix.site_dir,
            "PATH": os.pathsep.join(paths),
            "PYTHONNOUSERSITE": "1",
            "PDM_PYTHON_PEP582": "0",
        }

    def subprocess_runner(
        self,
        cmd: List[str],
        cwd: Optional[os.PathLike] = None,
        extra_environ: Optional[Dict[str, str]] = None,
        isolated: bool = True,
    ) -> None:
        env = self._env_vars.copy() if isolated else {}
        if extra_environ:
            env.update(extra_environ)
        return log_subprocessor(cmd, cwd, extra_environ=env)

    def check_requirements(self, reqs: Iterable[str]) -> Iterable[str]:
        missing = set()
        conflicting = set()
        if reqs:
            ws = WorkingSet(self._prefix.lib_dirs)
            for req in reqs:
                try:
                    if ws.find(Requirement.parse(req)) is None:
                        missing.add(req)
                except VersionConflict:
                    conflicting.add(req)
        if conflicting:
            raise BuildError(f"Conflicting requirements: {', '.join(conflicting)}")
        return missing

    def install(self, requirements: Iterable[str]) -> None:
        missing = self.check_requirements(requirements)
        if not missing:
            return

        with tempfile.NamedTemporaryFile(
            "w+", prefix="pdm-build-reqs-", suffix=".txt", delete=False
        ) as req_file:
            req_file.write(os.linesep.join(missing))
            req_file.close()
            cmd = self._env.pip_command + [
                "install",
                "--ignore-installed",
                "--prefix",
                self._path,
            ]
            cmd.extend(prepare_pip_source_args(self._env.project.sources))
            cmd.extend(["-r", req_file.name])
            self.subprocess_runner(cmd, isolated=False)
            os.unlink(req_file.name)

    def build(self, out_dir: str) -> str:
        """Build and store the artifact in out_dir,
        return the absolute path of the built result.
        """
        raise NotImplementedError("Should be implemented in subclass")
