import abc
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, List, Mapping, Optional, Tuple, Type

from pdm import termui
from pdm.cli.commands.venv.utils import get_venv_prefix
from pdm.exceptions import PdmUsageError, ProjectError
from pdm.models.python import PythonInfo
from pdm.project import Project
from pdm.utils import cached_property


class VirtualenvCreateError(ProjectError):
    pass


class Backend(abc.ABC):
    """The base class for virtualenv backends"""

    def __init__(self, project: Project, python: Optional[str]) -> None:
        self.project = project
        self.python = python

    @cached_property
    def _resolved_interpreter(self) -> PythonInfo:
        if not self.python:
            saved_python = self.project.project_config.get("python.path")
            if saved_python:
                return PythonInfo.from_path(saved_python)
        for py_version in self.project.find_interpreters(self.python):
            if (
                self.python
                or py_version.valid
                and self.project.python_requires.contains(py_version.version, True)
            ):
                return py_version

        python = f" {self.python}" if self.python else ""
        raise VirtualenvCreateError(f"Can't resolve python interpreter{python}")

    @property
    def ident(self) -> str:
        """Get the identifier of this virtualenv.
        self.python can be one of:
            3.8
            /usr/bin/python
            3.9.0a4
            python3.8
        """
        return self._resolved_interpreter.identifier

    def subprocess_call(self, cmd: List[str], **kwargs: Any) -> None:
        self.project.core.ui.echo(
            f"Run command: [green]{cmd}[/]", verbosity=termui.Verbosity.DETAIL, err=True
        )
        try:
            subprocess.check_call(
                cmd,
                stdout=subprocess.DEVNULL
                if self.project.core.ui.verbosity < termui.Verbosity.DETAIL
                else None,
            )
        except subprocess.CalledProcessError as e:  # pragma: no cover
            raise VirtualenvCreateError(e) from None

    def _ensure_clean(self, location: Path, force: bool = False) -> None:
        if not location.exists():
            return
        if not force:
            raise VirtualenvCreateError(f"The location {location} is not empty")
        self.project.core.ui.echo(
            f"Cleaning existing target directory {location}", err=True
        )
        shutil.rmtree(location)

    def get_location(self, name: Optional[str]) -> Path:
        venv_parent = Path(self.project.config["venv.location"])
        if not venv_parent.is_dir():
            venv_parent.mkdir(exist_ok=True, parents=True)
        return venv_parent / f"{get_venv_prefix(self.project)}{name or self.ident}"

    def create(
        self,
        name: Optional[str] = None,
        args: Tuple[str, ...] = (),
        force: bool = False,
        in_project: bool = False,
        prompt: Optional[str] = None,
    ) -> Path:
        if in_project:
            location = self.project.root / ".venv"
        else:
            location = self.get_location(name)
        if prompt is not None:
            prompt_string = prompt.format(
                project_name=self.project.root.name.lower() or "virtualenv",
                python_version=self.ident,
            )
            args = (*args, f"--prompt={prompt_string}")
        self._ensure_clean(location, force)
        self.perform_create(location, args)
        return location

    @abc.abstractmethod
    def perform_create(self, location: Path, args: Tuple[str, ...]) -> None:
        pass


class VirtualenvBackend(Backend):
    def perform_create(self, location: Path, args: Tuple[str, ...]) -> None:
        cmd = [
            sys.executable,
            "-m",
            "virtualenv",
            "--no-pip",
            "--no-setuptools",
            "--no-wheel",
            str(location),
        ]
        cmd.extend(["-p", str(self._resolved_interpreter.executable)])
        cmd.extend(args)
        self.subprocess_call(cmd)


class VenvBackend(VirtualenvBackend):
    def perform_create(self, location: Path, args: Tuple[str, ...]) -> None:
        cmd = [
            str(self._resolved_interpreter.executable),
            "-m",
            "venv",
            "--without-pip",
            str(location),
        ] + list(args)
        self.subprocess_call(cmd)


class CondaBackend(Backend):
    @property
    def ident(self) -> str:
        # Conda supports specifying python that doesn't exist,
        # use the passed-in name directly
        if self.python:
            return self.python
        return super().ident

    def perform_create(self, location: Path, args: Tuple[str, ...]) -> None:
        if self.python:
            python_ver = self.python
        else:
            python = self._resolved_interpreter
            python_ver = f"{python.major}.{python.minor}"
        if any(arg.startswith("python=") for arg in args):
            raise PdmUsageError("Cannot use python= in conda creation arguments")
        cmd = [
            "conda",
            "create",
            "--yes",
            "--prefix",
            str(location),
            f"python={python_ver}",
            *args,
        ]

        self.subprocess_call(cmd)


BACKENDS: Mapping[str, Type[Backend]] = {
    "virtualenv": VirtualenvBackend,
    "venv": VenvBackend,
    "conda": CondaBackend,
}
