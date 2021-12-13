import contextlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from time import monotonic
from typing import Any, Callable, Generator, Sequence, TypeVar

import click

PROJECT_DIR = Path(__file__).parent.joinpath("projects")


class Executor:
    def __init__(self, cmd: str, project_file: Path) -> None:
        self.cmd = cmd
        self.project_file = project_file
        self._backup_file = self.project_file.with_suffix(".bak")
        shutil.copy2(self.project_file, self._backup_file)

    def revert_file(self) -> None:
        shutil.copy2(self._backup_file, self.project_file)

    def run(self, args: Sequence[str], **kwargs: Any) -> subprocess.CompletedProcess:
        return subprocess.run(
            [self.cmd, *args],
            check=True,
            capture_output=True,
            cwd=self.project_file.parent.as_posix(),
            **kwargs,
        )

    def measure(
        self, text: str, args: Sequence[str], **kwargs: Any
    ) -> subprocess.CompletedProcess:
        time_start = monotonic()
        proc = self.run(args, **kwargs)
        time_cost = monotonic() - time_start
        click.echo(f"  {click.style(text + ':', fg='yellow')}\t\t{time_cost:.2f}s")
        return proc


TestFunc = Callable[[Executor], Any]
T = TypeVar("T", bound=TestFunc)


def project(cmd: str, project_file: str) -> Callable[[T], T]:
    def wrapper(func: T) -> T:
        func._meta = {"cmd": cmd, "project_file": project_file}
        return func

    return wrapper


@contextlib.contextmanager
def temp_env() -> Generator[None, None, None]:
    old_env = os.environ.copy()
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(old_env)


def benchmark(func: TestFunc) -> Any:
    meta = func._meta
    version = subprocess.check_output([meta["cmd"], "--version"]).strip().decode("utf8")
    click.secho(f"Running benchmark: {version}", fg="green")
    project_file = PROJECT_DIR.joinpath(meta["project_file"])
    with tempfile.TemporaryDirectory(prefix="pdm-benchmark-") as tempdir:
        if project_file.name.startswith("pyproject"):
            dest_file = Path(tempdir).joinpath("pyproject.toml")
        else:
            dest_file = Path(tempdir).joinpath(project_file.name)
        shutil.copy2(project_file, dest_file)
        executor = Executor(meta["cmd"], dest_file)
        with temp_env():
            return func(executor)
