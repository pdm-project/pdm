from __future__ import annotations

import functools
import multiprocessing
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from pdm import termui
from pdm._types import Distribution
from pdm.exceptions import InstallationError
from pdm.installers.manager import InstallManager
from pdm.models.candidates import Candidate
from pdm.models.environment import Environment
from pdm.models.requirements import parse_requirement, strip_extras
from pdm.utils import is_editable


class DummyFuture:
    _NOT_SET = object()

    def __init__(self) -> None:
        self._result = self._NOT_SET
        self._exc: Optional[Exception] = None

    def set_result(self, result: Any) -> None:
        self._result = result

    def set_exception(self, exc: Exception) -> None:
        self._exc = exc

    def result(self) -> Any:
        return self._result

    def exception(self) -> Optional[Exception]:
        return self._exc

    def add_done_callback(self, func: Callable) -> None:
        func(self)


class DummyExecutor:
    """A synchronous pool class to mimic ProcessPoolExecuter's interface.
    functions are called and awaited for the result
    """

    def submit(self, func: Callable, *args: str, **kwargs: Any) -> DummyFuture:
        future = DummyFuture()
        try:
            future.set_result(func(*args, **kwargs))
        except Exception as exc:
            future.set_exception(exc)
        return future

    def __enter__(self) -> DummyExecutor:
        return self

    def __exit__(self, *args: Any, **kwargs: Any) -> None:
        return


def editables_candidate(environment: Environment) -> Candidate | None:
    """Return a candidate for `editables` package"""
    with environment.get_finder() as finder:
        best_match = finder.find_best_candidate("editables")
        if best_match.best_candidate is None:
            return None
        return Candidate.from_installation_candidate(
            best_match.best_candidate, parse_requirement("editables"), environment
        )


class Synchronizer:
    """Synchronize the working set with given installation candidates"""

    SEQUENTIAL_PACKAGES = ("pip", "setuptools", "wheel")

    def __init__(
        self,
        candidates: Dict[str, Candidate],
        environment: Environment,
        clean: bool = False,
        dry_run: bool = False,
        retry_times: int = 1,
        install_self: bool = False,
        no_editable: bool = False,
        use_install_cache: bool = False,
        reinstall: bool = False,
    ) -> None:
        self.environment = environment
        self.clean = clean
        self.dry_run = dry_run
        self.retry_times = retry_times
        self.no_editable = no_editable
        self.install_self = install_self
        self.use_install_cache = use_install_cache
        self.reinstall = reinstall

        self.parallel = environment.project.config["parallel_install"]
        locked_repository = environment.project.locked_repository
        self.all_candidate_keys = list(locked_repository.all_candidates)
        self.working_set = environment.get_working_set()
        self.ui = environment.project.core.ui

        if self.no_editable:
            for candidate in candidates.values():
                candidate.req.editable = None  # type: ignore
        elif (
            self.install_self
            and getattr(self.environment.project.meta, "editable_backend", "editables")
            == "editables"
            and "editables" not in candidates
        ):
            # Install `editables` as well as required by self project
            editables = editables_candidate(environment)
            if editables is not None:
                candidates["editables"] = editables
        self.candidates = candidates
        self._manager: InstallManager | None = None

    def create_executor(
        self,
    ) -> Union[ThreadPoolExecutor, DummyExecutor]:
        if self.parallel:
            return ThreadPoolExecutor(max_workers=min(multiprocessing.cpu_count(), 8))
        else:
            return DummyExecutor()

    @property
    def manager(self) -> InstallManager:
        if not self._manager:
            self._manager = self.get_manager()
        return self._manager

    def get_manager(self) -> InstallManager:
        return self.environment.project.core.install_manager_class(
            self.environment, use_install_cache=self.use_install_cache
        )

    @property
    def self_key(self) -> Optional[str]:
        meta = self.environment.project.meta
        if meta.name:
            return meta.project_name.lower()
        return None

    def compare_with_working_set(self) -> Tuple[List[str], List[str], List[str]]:
        """Compares the candidates and return (to_add, to_update, to_remove)"""
        working_set = self.working_set
        candidates = self.candidates.copy()
        to_update, to_remove = [], []

        for key, dist in working_set.items():
            if key == self.self_key:
                continue
            if key in candidates:
                can = candidates.pop(key)
                if (
                    can.req.editable
                    or self.reinstall
                    or is_editable(dist)
                    or (dist.version != can.version)
                ):
                    to_update.append(key)
            elif (
                key not in self.all_candidate_keys
                and key not in self.SEQUENTIAL_PACKAGES
            ):
                # Remove package only if it is not required by any group
                # Packages for packaging will never be removed
                to_remove.append(key)
        to_add = list(
            {
                strip_extras(name)[0]
                for name, _ in candidates.items()
                if name != self.self_key and strip_extras(name)[0] not in working_set
            }
        )
        return (
            sorted(to_add),
            sorted(to_update),
            sorted(to_remove) if self.clean else [],
        )

    def install_candidate(self, key: str) -> Candidate:
        """Install candidate"""
        can = self.candidates[key]
        with self.ui.open_spinner(f"Installing {can.format()}...") as spinner:
            try:
                self.manager.install(can)
            except Exception:
                spinner.fail(f"Install {can.format()} failed")
                raise
            else:
                spinner.succeed(f"Install {can.format()} successful")

        return can

    def update_candidate(self, key: str) -> Tuple[Distribution, Candidate]:
        """Update candidate"""
        can = self.candidates[key]
        dist = self.working_set[strip_extras(key)[0]]
        dist_version = dist.version
        with self.ui.open_spinner(
            f"Updating {termui.green(key, bold=True)} {termui.yellow(dist.version)} "
            f"-> {termui.yellow(can.version)}..."
        ) as spinner:
            try:
                self.manager.uninstall(dist)
                self.manager.install(can)
            except Exception:
                spinner.fail(
                    f"Update {termui.green(key, bold=True)} "
                    f"{termui.yellow(dist_version)} -> "
                    f"{termui.yellow(can.version)} failed"
                )
                raise
            else:
                spinner.succeed(
                    f"Update {termui.green(key, bold=True)} "
                    f"{termui.yellow(dist_version)} -> "
                    f"{termui.yellow(can.version)} successful"
                )
        return dist, can

    def remove_distribution(self, key: str) -> Distribution:
        """Remove distributions with given names."""
        dist = self.working_set[key]
        dist_version = dist.version
        with self.ui.open_spinner(
            f"Removing {termui.green(key, bold=True)} {termui.yellow(dist.version)}..."
        ) as spinner:
            try:
                self.manager.uninstall(dist)
            except Exception:
                spinner.fail(
                    f"Remove {termui.green(key, bold=True)} "
                    f"{termui.yellow(dist_version)} failed"
                )
                raise
            else:
                spinner.succeed(
                    f"Remove {termui.green(key, bold=True)} "
                    f"{termui.yellow(dist_version)} successful"
                )
        return dist

    def _show_headline(self, packages: Dict[str, List[str]]) -> None:
        add, update, remove = packages["add"], packages["update"], packages["remove"]
        if not any((add, update, remove)):
            self.ui.echo("All packages are synced to date, nothing to do.\n")
            return
        results = [termui.bold("Synchronizing working set with lock file:")]
        results.extend(
            [
                f"{termui.green(str(len(add)))} to add,",
                f"{termui.yellow(str(len(update)))} to update,",
                f"{termui.red(str(len(remove)))} to remove",
            ]
        )
        self.ui.echo(" ".join(results) + "\n")

    def _show_summary(self, packages: Dict[str, List[str]]) -> None:
        to_add = [self.candidates[key] for key in packages["add"]]
        to_update = [
            (self.working_set[key], self.candidates[key]) for key in packages["update"]
        ]
        to_remove = [self.working_set[key] for key in packages["remove"]]
        lines = []
        if to_add:
            lines.append(termui.bold("Packages to add:"))
            for can in to_add:
                lines.append(f"  - {can.format()}")
        if to_update:
            lines.append(termui.bold("Packages to update:"))
            for prev, cur in to_update:
                lines.append(
                    f"  - {termui.green(cur.name, bold=True)} "
                    f"{termui.yellow(prev.version)} -> {termui.yellow(cur.version)}"
                )
        if to_remove:
            lines.append(termui.bold("Packages to remove:"))
            for dist in to_remove:
                lines.append(
                    f"  - {termui.green(dist.metadata['Name'], bold=True)} "
                    f"{termui.yellow(dist.version)}"
                )
        if lines:
            self.ui.echo("\n".join(lines))

    def synchronize(self) -> None:
        """Synchronize the working set with pinned candidates."""
        to_add, to_update, to_remove = self.compare_with_working_set()
        to_do = {"remove": to_remove, "update": to_update, "add": to_add}

        if self.dry_run:
            self._show_summary(to_do)
            return

        self._show_headline(to_do)
        handlers = {
            "add": self.install_candidate,
            "update": self.update_candidate,
            "remove": self.remove_distribution,
        }
        sequential_jobs = []
        parallel_jobs = []

        for kind in to_do:
            for key in to_do[kind]:
                if key in self.SEQUENTIAL_PACKAGES:
                    sequential_jobs.append((kind, key))
                elif key in self.candidates and self.candidates[key].req.editable:
                    # Editable packages are installed sequentially.
                    sequential_jobs.append((kind, key))
                else:
                    parallel_jobs.append((kind, key))

        errors: List[str] = []
        failed_jobs: List[Tuple[str, str]] = []

        def update_progress(
            future: Union[Future, DummyFuture], kind: str, key: str
        ) -> None:
            error = future.exception()
            if error:
                exc_info = (type(error), error, error.__traceback__)
                termui.logger.exception("Error occurs: ", exc_info=exc_info)
                failed_jobs.append((kind, key))
                errors.extend(
                    [f"{kind} {termui.green(key)} failed:\n"]
                    + traceback.format_exception(*exc_info)
                )

        with self.ui.logging("install"):
            with self.ui.indent("  "):
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
                    self.ui.echo("Retry failed jobs")

            if errors:
                self.ui.echo(termui.red("\nERRORS:"))
                self.ui.echo("".join(errors), err=True)
                raise InstallationError("Some package operations are not complete yet")

            if self.install_self:
                self_candidate = self.environment.project.make_self_candidate(
                    not self.no_editable
                )
                self_key = self.self_key
                assert self_key
                self.candidates[self_key] = self_candidate
                word = "a" if self.no_editable else "an editable"
                self.ui.echo(f"Installing the project as {word} package...")
                with self.ui.indent("  "):
                    if self_key in self.working_set:
                        self.update_candidate(self_key)
                    else:
                        self.install_candidate(self_key)

            self.ui.echo(f"\n{termui.Emoji.SUCC} All complete!")
