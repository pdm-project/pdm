from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import zipapp
import zipfile
from pathlib import Path
from tempfile import mkdtemp
from typing import TYPE_CHECKING, Iterable, List, Optional

import toml
from pep517.wrappers import Pep517HookCaller

from pdm.exceptions import BuildError
from pdm.iostream import stream
from pdm.pep517.base import Builder
from pdm.utils import get_python_version, get_sys_config_paths

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

    def __init__(self, logger, level):
        super().__init__()
        self.daemon = True

        self.logger = logger
        self.level = level

        # create the pipe and reader
        self.fd_read, self.fd_write = os.pipe()
        self.reader = os.fdopen(self.fd_read)

        self.start()

    def fileno(self):
        return self.fd_write

    @staticmethod
    def remove_newline(msg):
        return msg[:-1] if msg.endswith("\n") else msg

    def run(self):
        for line in self.reader:
            self._write(self.remove_newline(line))

    def _write(self, message):
        self.logger.log(self.level, message)


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


def _download_and_make_pip_pyz(path):
    dirname = tempfile.mkdtemp(prefix="pip-download-")
    try:
        log_subprocessor(
            [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--only-binary=:all:",
                "-d",
                dirname,
                "pip",
            ]
        )
        wheel_file = next(Path(dirname).glob("pip-*.whl"))
        with zipfile.ZipFile(wheel_file, "r") as zf:
            zf.extractall(Path(dirname) / "extracted")
        zipapp.create_archive(Path(dirname) / "extracted/pip", path)
    finally:
        shutil.rmtree(dirname, ignore_errors=True)


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
        self._path = None  # type: Optional[str]
        self.executable = self._env.python_executable
        self.pip_command = self._get_pip_command()
        self.src_dir = src_dir
        self._saved_env = None

        try:
            with open(os.path.join(src_dir, "pyproject.toml")) as f:
                spec = toml.load(f)
        except FileNotFoundError:
            spec = {}
        except Exception as e:
            raise BuildError(e) from e
        self._build_system = spec.get("build-system", self.DEFAULT_BACKEND)

        if "build-backend" not in self._build_system:
            self._build_system["build-backend"] = self.DEFAULT_BACKEND["build-backend"]
            self._build_system["requires"] = (
                self._build_system.get("requires", [])
                + self.DEFAULT_BACKEND["requires"]
            )

        if "requires" not in self._build_system:
            raise BuildError("Missing 'build-system.requires' in pyproject.toml")

        self._backend = self._build_system["build-backend"]

        self._hook = Pep517HookCaller(
            src_dir,
            self._backend,
            backend_path=self._build_system.get("backend-path"),
            python_executable=self.executable,
        )

    def _get_pip_command(self) -> List[str]:
        """Get a pip command that has pip installed.
        E.g: ['python', '-m', 'pip']
        """
        python_version = get_python_version(self.executable)
        proc = subprocess.run(
            [self.executable, "-m", "pip", "--version"], capture_output=True
        )
        if proc.returncode == 0:
            # The pip has already been installed with the executable, just use it
            return [self.executable, "-m", "pip"]
        if python_version[0] == 3:
            # Use the ensurepip to provision one.
            try:
                log_subprocessor(
                    [self.executable, "-Im", "ensurepip", "--upgrade", "--default-pip"]
                )
            except BuildError:
                pass
            else:
                return [self.executable, "-m", "pip"]
        # Otherwise, download a zipball pip from the Internet.
        pip_pyz = self._env.project.cache("pip.pyz")
        if not pip_pyz.is_file():
            _download_and_make_pip_pyz(pip_pyz)
        return [self.executable, pip_pyz]

    def __enter__(self):
        self._path = mkdtemp(prefix="pdm-build-env-")
        self.install(self._build_system["requires"])
        paths = get_sys_config_paths(
            self.executable, vars={"base": self._path, "platbase": self._path}
        )
        self._saved_env = {
            name: os.environ.get(name, None)
            for name in ("PATH", "PYTHONNOUSERSITE", "PYTHONPATH")
        }
        old_path = os.getenv("PATH")
        os.environ.update(
            {
                "PYTHONPATH": paths["purelib"],
                "PATH": paths["scripts"]
                if not old_path
                else os.pathsep.join([paths["scripts"], old_path]),
                "PYTHONNOUSERSITE": "1",
            }
        )
        stream.logger.debug("Preparing isolated env for PEP 517 build...")
        return self

    def __exit__(self, *args):
        for key, value in self._saved_env.items():
            if value is None:
                del os.environ[key]
            else:
                os.environ[key] = value
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
            log_subprocessor(cmd)
            os.unlink(req_file.name)

    def build_wheel(self, out_dir: str) -> str:
        """Build wheel and return the full path of the artifact."""
        with self._hook.subprocess_runner(log_subprocessor):
            requires = self._hook.get_requires_for_build_wheel()
            self.install(requires)
            filename = self._hook.build_wheel(out_dir)
        return os.path.join(out_dir, filename)

    def build_sdist(self, out_dir: str) -> str:
        """Build sdist and return the full path of the artifact."""
        with self._hook.subprocess_runner(log_subprocessor):
            requires = self._hook.get_requires_for_build_sdist()
            self.install(requires)
            filename = self._hook.build_sdist(out_dir)
        return os.path.join(out_dir, filename)

    def build_egg_info(self, out_dir: str) -> str:
        # Ignore destination since editable builds should be build locally
        builder = Builder(self.src_dir)
        setup_py_path = builder.ensure_setup_py().as_posix()
        self.install(["setuptools"])
        args = [self.executable, "-c", _SETUPTOOLS_SHIM.format(setup_py_path)]
        args.extend(["egg_info", "--egg-base", out_dir])
        log_subprocessor(args, cwd=self.src_dir)
        filename = _find_egg_info(out_dir)
        return os.path.join(out_dir, filename)
