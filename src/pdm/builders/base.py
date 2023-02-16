from __future__ import annotations

import logging
import os
import shutil
import subprocess
import textwrap
import threading
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Mapping, cast

from pyproject_hooks import BuildBackendHookCaller

from pdm.compat import tomllib
from pdm.exceptions import BuildError
from pdm.models.environment import PrefixEnvironment
from pdm.models.in_process import get_sys_config_paths
from pdm.models.requirements import Requirement, parse_requirement
from pdm.models.working_set import WorkingSet
from pdm.termui import logger
from pdm.utils import create_tracked_tempdir

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

        self.start()
        self._output_buffer: list[str] = []

    def fileno(self) -> int:
        return self.fd_write

    @staticmethod
    def remove_newline(msg: str) -> str:
        return msg[:-1] if msg.endswith("\n") else msg

    def run(self) -> None:
        with os.fdopen(self.fd_read, encoding="utf-8", errors="replace") as reader:
            for line in reader:
                self._write(self.remove_newline(line))

    def _write(self, message: str) -> None:
        self.logger.log(self.level, message)
        self._output_buffer.append(message)
        if len(self._output_buffer) > 10:
            self._output_buffer[:-10] = []

    def stop(self) -> None:
        os.close(self.fd_write)
        self.join()


def build_error(e: subprocess.CalledProcessError) -> BuildError:
    """Get a build error with meaningful error message
    from the subprocess output.
    """
    output = cast("list[str]", e.output)
    errors: list[str] = []
    if output[-1].strip().startswith("ModuleNotFoundError"):
        package = output[-1].strip().split()[-1]
        errors.append(
            f"Module {package} is missing, please make sure it is specified in the "
            "'build-system.requires' section. If it is not possible, "
            "add it to the project and use '--no-isolation' option."
        )
    errors.extend(["Showing the last 10 lines of the build output:", *output])
    error_message = "\n".join(errors)
    return BuildError(f"Build backend raised error: {error_message}")


def log_subprocessor(
    cmd: list[str],
    cwd: str | Path | None = None,
    extra_environ: dict[str, str] | None = None,
) -> None:
    env = os.environ.copy()
    if extra_environ:
        env.update(extra_environ)
    outstream = LoggerWrapper(logger, logging.INFO)
    try:
        subprocess.check_call(
            cmd,
            cwd=cwd,
            env=env,
            stdout=outstream.fileno(),
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError as e:
        e.output = outstream._output_buffer
        raise build_error(e) from None
    finally:
        outstream.stop()


class _Prefix:
    def __init__(self, executable: str, shared: str, overlay: str) -> None:
        self.bin_dirs: list[str] = []
        self.lib_dirs: list[str] = []
        for path in (overlay, shared):
            paths = get_sys_config_paths(executable, vars={"base": path, "platbase": path}, kind="prefix")
            self.bin_dirs.append(paths["scripts"])
            self.lib_dirs.extend([paths["platlib"], paths["purelib"]])
        self.site_dir = os.path.join(overlay, "site")
        if os.path.isdir(self.site_dir):
            # Clear existing site dir as .pyc may be cached.
            shutil.rmtree(self.site_dir)
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
        _hook: BuildBackendHookCaller
        _requires: list[str]
        _prefix: _Prefix

    @classmethod
    def get_shared_env(cls, key: int) -> str:
        if key in cls._shared_envs:
            logger.debug("Reusing shared build env: %s", cls._shared_envs[key])
            return cls._shared_envs[key]
        # We don't save the cache here, instead it will be done after the installation
        # finished.
        return create_tracked_tempdir("-shared", "pdm-build-env-")

    @classmethod
    def get_overlay_env(cls, key: str) -> str:
        if key not in cls._overlay_envs:
            cls._overlay_envs[key] = create_tracked_tempdir("-overlay", "pdm-build-env-")
        return cls._overlay_envs[key]

    def __init__(self, src_dir: str | Path, environment: Environment) -> None:
        """If isolated is True(default), the builder will set up a *clean* environment.
        Otherwise, the environment of the host Python will be used.
        """
        self._env = environment
        self.executable = self._env.interpreter.executable.as_posix()
        self.src_dir = src_dir
        self.isolated = environment.project.config["build_isolation"]
        logger.info("Preparing isolated env for PEP 517 build...")
        try:
            with open(os.path.join(src_dir, "pyproject.toml"), "rb") as f:
                spec = tomllib.load(f)
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

    def init_build_system(self, build_system: dict[str, Any]) -> None:
        """Initialize the build system and requires list from the PEP 517 spec"""
        self._hook = BuildBackendHookCaller(
            self.src_dir,
            build_system["build-backend"],
            backend_path=build_system.get("backend-path"),
            runner=self.subprocess_runner,
            python_executable=self.executable,
        )
        self._requires = build_system["requires"]
        self._prefix = _Prefix(
            self.executable,
            # Build backends with the same requires list share the cached base env.
            shared=self.get_shared_env(hash(frozenset(self._requires))),
            # Overlay envs are unique for each source to be built.
            overlay=self.get_overlay_env(os.path.normcase(self.src_dir).rstrip("\\/")),
        )

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
            pythonpath = [*self._prefix.lib_dirs, project_libs]
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

    def check_requirements(self, reqs: Iterable[str]) -> Iterable[Requirement]:
        missing = set()
        conflicting = set()
        project_lib = self._env.get_paths()["purelib"]
        libs = self._prefix.lib_dirs + ([project_lib] if not self.isolated else [])
        if reqs:
            ws = WorkingSet(libs)
            marker_env = self._env.marker_environment
            for req in reqs:
                parsed_req = parse_requirement(req)
                if parsed_req.marker and not parsed_req.marker.evaluate(marker_env):
                    logger.debug(
                        "Skipping requirement %s: mismatching marker %s",
                        req,
                        parsed_req.marker,
                    )
                    continue
                if parsed_req.identify() not in ws:
                    missing.add(parsed_req)
                elif parsed_req.specifier and not parsed_req.specifier.contains(
                    ws[parsed_req.identify()].version, prereleases=True
                ):
                    conflicting.add(req)
        if conflicting:
            raise BuildError(f"Conflicting requirements: {', '.join(conflicting)}")
        return missing

    def install(self, requirements: Iterable[str], shared: bool = False) -> None:
        from pdm.installers.core import install_requirements

        missing = list(self.check_requirements(requirements))
        if not missing:
            return
        path = self._prefix.shared if shared else self._prefix.overlay
        env = PrefixEnvironment(self._env.project, path)
        install_requirements(missing, env)

        if shared:
            # The shared env is prepared and is safe to be cached now. This is to make
            # sure no broken env is returned early when run in parallel mode.
            key = hash(frozenset(requirements))
            if key not in self._shared_envs:
                self._shared_envs[key] = path

    def prepare_metadata(self, out_dir: str, config_settings: Mapping[str, Any] | None = None) -> str:
        """Prepare metadata and store in the out_dir.
        Some backends doesn't provide that API, in that case the metadata will be
        retrieved from the built result.
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
