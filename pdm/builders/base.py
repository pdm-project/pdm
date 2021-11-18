from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import textwrap
import threading
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Mapping

import tomli
from pep517.wrappers import Pep517HookCaller

from pdm.exceptions import BuildError
from pdm.models.in_process import get_sys_config_paths
from pdm.models.requirements import parse_requirement
from pdm.models.working_set import WorkingSet
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

        self.start()

    def fileno(self) -> int:
        return self.fd_write

    @staticmethod
    def remove_newline(msg: str) -> str:
        return msg[:-1] if msg.endswith("\n") else msg

    def run(self) -> None:
        try:
            for line in self.reader:
                self._write(self.remove_newline(line))
        finally:
            self.reader.close()

    def _write(self, message: str) -> None:
        self.logger.log(self.level, message)

    def stop(self) -> None:
        os.close(self.fd_write)
        self.join()


def log_subprocessor(
    cmd: list[str],
    cwd: str | Path | None = None,
    extra_environ: dict[str, str] | None = None,
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
    except subprocess.CalledProcessError as e:
        raise BuildError(
            f"Call command {cmd} return non-zero status({e.returncode})."
        ) from None
    finally:
        outstream.stop()


class _Prefix:
    def __init__(self, executable: str, shared: str, overlay: str) -> None:
        self.bin_dirs: list[str] = []
        self.lib_dirs: list[str] = []
        for path in (overlay, shared):
            paths = get_sys_config_paths(
                executable, vars={"base": path, "platbase": path}
            )
            self.bin_dirs.append(paths["scripts"])
            self.lib_dirs.extend([paths["platlib"], paths["purelib"]])
        self.site_dir = os.path.join(path, "site")
        if not os.path.isdir(self.site_dir):
            os.makedirs(self.site_dir)
        with open(os.path.join(self.site_dir, "sitecustomize.py"), "w") as fp:
            fp.write(
                textwrap.dedent(
                    f"""
                import sys, os, site

                original_sys_path = sys.path[:]
                known_paths = set()
                site.addusersitepackages(known_paths)
                site.addsitepackages(known_paths)
                known_paths = {{os.path.normcase(p) for p in known_paths}}
                original_sys_path = [
                    p for p in original_sys_path
                    if os.path.normcase(p) not in known_paths]
                sys.path[:] = original_sys_path
                for lib_path in {self.lib_dirs!r}:
                    site.addsitedir(lib_path)
                """
                )
            )
        self.shared = shared
        self.overlay = overlay


class EnvBuilder:
    """A simple PEP 517 builder for an isolated environment"""

    DEFAULT_BACKEND = {
        "build-backend": "setuptools.build_meta:__legacy__",
        "requires": ["setuptools >= 40.8.0", "wheel"],
    }

    _shared_envs: dict[int, str] = {}
    _overlay_envs: dict[str, str] = {}

    if TYPE_CHECKING:
        _hook: Pep517HookCaller
        _requires: list[str]

    @classmethod
    def get_shared_env(cls, key: int) -> str:
        if key in cls._shared_envs:
            logger.debug("Reusing shared build env: %s", cls._shared_envs[key])
            return cls._shared_envs[key]
        # Postpone the cache after installation is done
        return create_tracked_tempdir("-shared", "pdm-build-env-")

    @classmethod
    def get_overlay_env(cls, key: str) -> str:
        if key not in cls._overlay_envs:
            cls._overlay_envs[key] = create_tracked_tempdir(
                "-overlay", "pdm-build-env-"
            )
        return cls._overlay_envs[key]

    def __init__(self, src_dir: str | Path, environment: Environment) -> None:
        """If isolated is True(default), the builder will set up a *clean* environment.
        Otherwise, the environment of the host Python will be used.
        """
        self._env = environment
        self.executable = self._env.interpreter.executable
        self.src_dir = src_dir
        self.isolated = environment.project.config["build_isolation"]
        logger.debug("Preparing isolated env for PEP 517 build...")
        try:
            with open(os.path.join(src_dir, "pyproject.toml"), "rb") as f:
                spec = tomli.load(f)
        except FileNotFoundError:
            spec = {}
        except Exception as e:
            raise BuildError(e) from e
        build_system = spec.get("build-system", self.DEFAULT_BACKEND)

        if "build-backend" not in build_system:
            build_system["build-backend"] = self.DEFAULT_BACKEND["build-backend"]

        if "requires" not in build_system:
            raise BuildError("Missing 'build-system.requires' in pyproject.toml")

        self.init_build_system(build_system)
        self._prefix = _Prefix(
            self.executable,
            shared=self.get_shared_env(hash(frozenset(self._requires))),
            overlay=self.get_overlay_env(os.path.normcase(self.src_dir).rstrip("\\/")),
        )

    def init_build_system(self, build_system: dict[str, Any]) -> None:
        """Initialize the build system and requires list from the PEP 517 spec"""
        self._hook = Pep517HookCaller(
            self.src_dir,
            build_system["build-backend"],
            backend_path=build_system.get("backend-path"),
            runner=self.subprocess_runner,
            python_executable=self.executable,
        )
        self._requires = build_system["requires"]
        if build_system["build-backend"].startswith("setuptools"):
            self.ensure_setup_py()

    @property
    def _env_vars(self) -> dict[str, str]:
        paths = self._prefix.bin_dirs
        if "PATH" in os.environ:
            paths.append(os.getenv("PATH", ""))
        env = {"PATH": os.pathsep.join(paths)}
        if self.isolated:
            env.update(
                {
                    "PYTHONPATH": self._prefix.site_dir,
                    "PYTHONNOUSERSITE": "1",
                }
            )
        else:
            project_libs = self._env.get_paths()["purelib"]
            pythonpath = self._prefix.lib_dirs + [project_libs]
            if "PYTHONPATH" in os.environ:
                pythonpath.append(os.getenv("PYTHONPATH", ""))
            env.update(
                PYTHONPATH=os.pathsep.join(pythonpath),
            )
        return env

    def subprocess_runner(
        self,
        cmd: list[str],
        cwd: str | Path | None = None,
        extra_environ: dict[str, str] | None = None,
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
                parsed_req = parse_requirement(req)
                if parsed_req.identify() not in ws:
                    missing.add(req)
                elif parsed_req.specifier and not parsed_req.specifier.contains(
                    ws[parsed_req.identify()].version, prereleases=True
                ):
                    conflicting.add(req)
        if conflicting:
            raise BuildError(f"Conflicting requirements: {', '.join(conflicting)}")
        return missing

    def install(self, requirements: Iterable[str], shared: bool = False) -> None:
        missing = self.check_requirements(requirements)
        if not missing:
            return
        path = self._prefix.shared if shared else self._prefix.overlay

        with tempfile.NamedTemporaryFile(
            "w+", prefix="pdm-build-reqs-", suffix=".txt", delete=False
        ) as req_file:
            req_file.write(os.linesep.join(missing))
            req_file.close()
            cmd = self._env.pip_command + [
                "install",
                "--isolated",
                "--ignore-installed",
                "--prefix",
                path,
            ]
            cmd.extend(prepare_pip_source_args(self._env.project.sources))
            cmd.extend(["-r", req_file.name])
            self.subprocess_runner(cmd, isolated=False)
            os.unlink(req_file.name)

        if shared:
            # The shared env is prepared and is safe to be cached now. This is to make
            # sure no broken env is returned when run in parallel mode.
            key = hash(frozenset(requirements))
            if key not in self._shared_envs:
                self._shared_envs[key] = path

    def prepare_metadata(
        self, out_dir: str, config_settings: Mapping[str, Any] | None = None
    ) -> str:
        """Prepare metadata and store in the out_dir. Some backends doesn't provide that API,
        in that case the metadata will be retrieved from the built result.
        """
        raise NotImplementedError("Should be implemented in subclass")

    def build(
        self,
        out_dir: str,
        config_settings: Mapping[str, Any] | None = None,
        metadata_directory: str | None = None,
    ) -> str:
        """Build and store the artifact in out_dir,
        return the absolute path of the built result.
        """
        raise NotImplementedError("Should be implemented in subclass")

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
