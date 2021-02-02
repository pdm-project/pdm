import contextlib
import functools
import multiprocessing
import traceback
from concurrent.futures.thread import ThreadPoolExecutor
from typing import Dict, List, Tuple

from pip._vendor.pkg_resources import Distribution, safe_name

from pdm.exceptions import InstallationError
from pdm.installers.installers import Installer, is_dist_editable
from pdm.iostream import CELE, stream
from pdm.models.builders import EnvBuilder
from pdm.models.candidates import Candidate
from pdm.models.environment import Environment
from pdm.models.requirements import strip_extras


class DummyFuture:
    _NOT_SET = object()

    def __init__(self):
        self._result = self._NOT_SET
        self._exc = None

    def set_result(self, result):
        self._result = result

    def set_exception(self, exc):
        self._exc = exc

    def result(self):
        return self._result

    def exception(self):
        return self._exc

    def add_done_callback(self, func):
        func(self)


class DummyExecutor:
    """A synchronous pool class to mimick ProcessPoolExecuter's interface.
    functions are called and awaited for the result
    """

    def submit(self, func, *args, **kwargs):
        future = DummyFuture()
        try:
            future.set_result(func(*args, **kwargs))
        except Exception as exc:
            future.set_exception(exc)
        return future

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        return


class Synchronizer:
    """Synchronize the working set with given installation candidates"""

    SEQUENTIAL_PACKAGES = ("pip", "setuptools", "wheel")

    def __init__(
        self,
        candidates: Dict[str, Candidate],
        environment: Environment,
        retry_times: int = 1,
    ) -> None:
        self.candidates = candidates
        self.environment = environment
        self.parallel = environment.project.config["parallel_install"]
        self.all_candidates = environment.project.get_locked_candidates("__all__")
        self.working_set = environment.get_working_set()
        self.retry_times = retry_times

    @contextlib.contextmanager
    def create_executor(self):
        if self.parallel:
            executor = ThreadPoolExecutor(
                max_workers=min(multiprocessing.cpu_count(), 8)
            )
        else:
            executor = DummyExecutor()
        with executor:
            try:
                yield executor
            except KeyboardInterrupt:
                pass

    def update_project_egg_info(self):
        if not self.environment.project.meta.name:
            return
        canonical_name = self.environment.project.meta.project_name.lower().replace(
            "-", "_"
        )
        egg_info_dir = self.environment.project.root / f"{canonical_name}.egg-info"
        if egg_info_dir.exists():
            stream.echo("Updating the project's egg info...")
            with EnvBuilder(self.environment.project.root, self.environment) as builder:
                builder.build_egg_info(str(builder.src_dir))

    def get_installer(self) -> Installer:
        return Installer(self.environment)

    def compare_with_working_set(self) -> Tuple[List[str], List[str], List[str]]:
        """Compares the candidates and return (to_add, to_update, to_remove)"""
        working_set = self.working_set
        to_update, to_remove = [], []
        candidates = self.candidates.copy()
        environment = self.environment.marker_environment
        for key, dist in working_set.items():
            if key in candidates:
                can = candidates.pop(key)
                if can.marker and not can.marker.evaluate(environment):
                    to_remove.append(key)
                elif not is_dist_editable(dist) and dist.version != can.version:
                    # XXX: An editable distribution is always considered as consistent.
                    to_update.append(key)
            elif key not in self.all_candidates and key not in self.SEQUENTIAL_PACKAGES:
                # Remove package only if it is not required by any section
                # Packages for packaging will never be removed
                to_remove.append(key)
        to_add = list(
            {
                strip_extras(name)[0]
                for name, can in candidates.items()
                if not (can.marker and not can.marker.evaluate(environment))
                and strip_extras(name)[0] not in working_set
            }
        )
        return sorted(to_add), sorted(to_update), sorted(to_remove)

    def install_candidate(self, key: str) -> Candidate:
        """Install candidate"""
        can = self.candidates[key]
        installer = self.get_installer()
        with stream.open_spinner(f"Installing {can.format()}...") as spinner:
            try:
                installer.install(can)
            except Exception:
                spinner.fail(f"Install {can.format()} failed")
                raise
            else:
                spinner.succeed(f"Install {can.format()} successful")

        return can

    def update_candidate(self, key: str) -> Tuple[Distribution, Candidate]:
        """Update candidate"""
        can = self.candidates[key]
        dist = self.working_set[safe_name(can.name).lower()]
        installer = self.get_installer()
        with stream.open_spinner(
            f"Updating {stream.green(key, bold=True)} {stream.yellow(dist.version)} "
            f"-> {stream.yellow(can.version)}..."
        ) as spinner:
            try:
                installer.uninstall(dist)
                installer.install(can)
            except Exception:
                spinner.fail(
                    f"Update {stream.green(key, bold=True)} "
                    f"{stream.yellow(dist.version)} -> "
                    f"{stream.yellow(can.version)} failed"
                )
                raise
            else:
                spinner.succeed(
                    f"Update {stream.green(key, bold=True)} "
                    f"{stream.yellow(dist.version)} -> "
                    f"-> {stream.yellow(can.version)} successful"
                )
        return dist, can

    def remove_distribution(self, key: str) -> Distribution:
        """Remove distributions with given names.

        :param distributions: a list of names to be removed.
        """
        installer = self.get_installer()
        dist = self.working_set[key]
        with stream.open_spinner(
            f"Removing {stream.green(key, bold=True)} {stream.yellow(dist.version)}..."
        ) as spinner:
            try:
                installer.uninstall(dist)
            except Exception:
                spinner.fail(
                    f"Remove {stream.green(key, bold=True)} "
                    f"{stream.yellow(dist.version)} failed"
                )
                raise
            else:
                spinner.succeed(
                    f"Remove {stream.green(key, bold=True)} "
                    f"{stream.yellow(dist.version)} successful"
                )
        return dist

    def _show_headline(self, packages: Dict[str, List[str]]) -> None:
        add, update, remove = packages["add"], packages["update"], packages["remove"]
        results = [stream.bold("Synchronizing working set with lock file:")]
        results.extend(
            [
                f"{stream.green(str(len(add)))} to add,",
                f"{stream.yellow(str(len(update)))} to update,",
                f"{stream.red(str(len(remove)))} to remove",
            ]
        )
        stream.echo(" ".join(results) + "\n")

    def _show_summary(self, packages: Dict[str, List[str]]) -> None:
        to_add = [self.candidates[key] for key in packages["add"]]
        to_update = [
            (self.working_set[key], self.candidates[key]) for key in packages["update"]
        ]
        to_remove = [self.working_set[key] for key in packages["remove"]]
        lines = []
        if to_add:
            lines.append(stream.bold("Packages to add:"))
            for can in to_add:
                lines.append(f"  - {can.format()}")
        if to_update:
            lines.append(stream.bold("Packages to add:"))
            for prev, cur in to_update:
                lines.append(
                    f"  - {stream.green(cur.name, bold=True)} "
                    f"{stream.yellow(prev.version)} -> {stream.yellow(cur.version)}"
                )
        if to_remove:
            lines.append(stream.bold("Packages to add:"))
            for dist in to_remove:
                lines.append(
                    f"  - {stream.green(dist.key, bold=True)} "
                    f"{stream.yellow(dist.version)}"
                )
        stream.echo("\n".join(lines))

    def synchronize(self, clean: bool = True, dry_run: bool = False) -> None:
        """Synchronize the working set with pinned candidates.

        :param clean: Whether to remove unneeded packages, defaults to True.
        :param dry_run: If set to True, only prints actions without actually do them.
        """
        to_add, to_update, to_remove = self.compare_with_working_set()
        if not clean:
            to_remove = []
        if not any([to_add, to_update, to_remove]):
            stream.echo(
                stream.yellow("All packages are synced to date, nothing to do.")
            )
            if not dry_run:
                with stream.logging("install"):
                    self.update_project_egg_info()
            return
        to_do = {"remove": to_remove, "update": to_update, "add": to_add}
        self._show_headline(to_do)

        if dry_run:
            self._show_summary(to_do)
            return

        handlers = {
            "add": self.install_candidate,
            "update": self.update_candidate,
            "remove": self.remove_distribution,
        }

        sequential_jobs = []
        parallel_jobs = []
        # Self package will be installed after all other dependencies are installed.
        install_self = None
        for kind in to_do:
            for key in to_do[kind]:
                if (
                    key == self.environment.project.meta.name
                    and self.environment.project.meta.project_name.lower()
                ):
                    install_self = (kind, key)
                elif key in self.SEQUENTIAL_PACKAGES:
                    sequential_jobs.append((kind, key))
                elif key in self.candidates and self.candidates[key].req.editable:
                    # Editable packages are installed sequentially.
                    sequential_jobs.append((kind, key))
                else:
                    parallel_jobs.append((kind, key))

        errors: List[str] = []
        failed_jobs: List[Tuple[str, str]] = []

        def update_progress(future, kind, key):
            if future.exception():
                failed_jobs.append((kind, key))
                error = future.exception()
                errors.extend(
                    [f"{kind} {stream.green(key)} failed:\n"]
                    + traceback.format_exception(
                        type(error), error, error.__traceback__
                    )
                )

        with stream.logging("install"), self.environment.activate():
            with stream.indent("  "):
                for job in sequential_jobs:
                    kind, key = job
                    handlers[kind](key)
                for i in range(self.retry_times + 1):
                    with self.create_executor() as executor:
                        for job in parallel_jobs:
                            kind, key = job
                            future = executor.submit(handlers[kind], key)
                            future.add_done_callback(
                                functools.partial(update_progress, kind=kind, key=key)
                            )
                    if not failed_jobs or i == self.retry_times:
                        break
                    parallel_jobs, failed_jobs = failed_jobs, []
                    errors.clear()
                    stream.echo("Retry failed jobs")

            if errors:
                stream.echo(stream.red("\nERRORS:"))
                stream.echo("".join(errors), err=True)
                raise InstallationError("Some package operations are not complete yet")

            if install_self:
                stream.echo("Installing the project as an editable package...")
                with stream.indent("  "):
                    handlers[install_self[0]](install_self[1])
            else:
                self.update_project_egg_info()
            stream.echo(f"\n{CELE} All complete!")
