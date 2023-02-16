from __future__ import annotations

import dataclasses
import functools
import multiprocessing
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from typing import TYPE_CHECKING, Any, Callable, Collection, TypeVar

from rich.progress import SpinnerColumn

from pdm import termui
from pdm.exceptions import InstallationError
from pdm.installers.manager import InstallManager
from pdm.models.candidates import Candidate, make_candidate
from pdm.models.environment import Environment
from pdm.models.requirements import Requirement, parse_requirement, strip_extras
from pdm.utils import is_editable, normalize_name

if TYPE_CHECKING:
    from rich.progress import Progress

    from pdm.compat import Distribution


_T = TypeVar("_T")


class DummyFuture:
    _NOT_SET = object()

    def __init__(self) -> None:
        self._result = self._NOT_SET
        self._exc: Exception | None = None

    def set_result(self, result: Any) -> None:
        self._result = result

    def set_exception(self, exc: Exception) -> None:
        self._exc = exc

    def result(self) -> Any:
        return self._result

    def exception(self) -> Exception | None:
        return self._exc

    def add_done_callback(self: _T, func: Callable[[_T], Any]) -> None:
        func(self)


class DummyExecutor:
    """A synchronous pool class to mimic ProcessPoolExecuter's interface.
    functions are called and awaited for the result
    """

    def submit(self, func: Callable, *args: Any, **kwargs: Any) -> DummyFuture:
        future = DummyFuture()
        try:
            future.set_result(func(*args, **kwargs))
        except Exception as exc:
            future.set_exception(exc)
        return future

    def __enter__(self: _T) -> _T:
        return self

    def __exit__(self, *args: Any, **kwargs: Any) -> None:
        return


def editables_candidate(environment: Environment) -> Candidate | None:
    """Return a candidate for `editables` package"""
    repository = environment.project.get_repository()
    return next(iter(repository.find_candidates(parse_requirement("editables"))), None)


class Synchronizer:
    """Synchronize the working set with given installation candidates

    :param candidates: a dict of candidates to be installed
    :param environment: the environment associated with the project
    :param clean: clean unneeded packages
    :param dry_run: only prints summary but do not install or uninstall
    :param retry_times: retry times when installation failed
    :param install_self: whether to install self project
    :param no_editable: if True, override all editable installations,
        if a list, override editables with the given names
    :param use_install_cache: whether to use install cache
    :param reinstall: whether to reinstall all packages
    :param only_keep: If true, only keep the selected candidates
    """

    SEQUENTIAL_PACKAGES = ("pip", "setuptools", "wheel")

    def __init__(
        self,
        candidates: dict[str, Candidate],
        environment: Environment,
        clean: bool = False,
        dry_run: bool = False,
        retry_times: int = 1,
        install_self: bool = False,
        no_editable: bool | Collection[str] = False,
        use_install_cache: bool = False,
        reinstall: bool = False,
        only_keep: bool = False,
    ) -> None:
        self.environment = environment
        self.clean = clean
        self.dry_run = dry_run
        self.retry_times = retry_times
        self.no_editable = no_editable
        self.install_self = install_self
        self.use_install_cache = use_install_cache
        self.reinstall = reinstall
        self.only_keep = only_keep

        self.parallel = environment.project.config["install.parallel"]
        locked_repository = environment.project.locked_repository
        self.all_candidate_keys = list(locked_repository.all_candidates)
        self.working_set = environment.get_working_set()
        self.ui = environment.project.core.ui
        self.self_candidate: Candidate | None = None
        if self.install_self:
            self.self_candidate = self.environment.project.make_self_candidate(not self.no_editable)

        if isinstance(self.no_editable, Collection):
            keys = self.no_editable
        elif self.no_editable:
            keys = candidates.keys()
        else:
            keys = []
            if self.should_install_editables() and "editables" not in candidates:
                # Install `editables` as well as required by self project
                editables = editables_candidate(environment)
                if editables is not None:
                    candidates["editables"] = editables
        for key in keys:
            if key in candidates and candidates[key].req.editable:
                # We do not do in-place update, which will break the caches
                candidate = candidates[key]
                req = dataclasses.replace(candidate.req, editable=False)
                candidates[key] = make_candidate(req, candidate.name, candidate.version, candidate.link)
        self.candidates = candidates
        self._manager: InstallManager | None = None

    def should_install_editables(self) -> bool:
        if self.self_candidate is None:
            return False
        metadata = self.self_candidate.prepare(self.environment).metadata
        return any(req.startswith("editables") for req in metadata.requires or [])

    def create_executor(
        self,
    ) -> ThreadPoolExecutor | DummyExecutor:
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
    def self_key(self) -> str | None:
        name = self.environment.project.name
        if name:
            return normalize_name(name)
        return name

    def _should_update(self, dist: Distribution, can: Candidate) -> bool:
        """Check if the candidate should be updated"""
        backend = self.environment.project.backend
        if self.reinstall or can.req.editable:  # Always update if incoming is editable
            return True
        if is_editable(dist):  # only update editable if no_editable is True
            return bool(self.no_editable)
        if not can.req.is_named:
            dreq = Requirement.from_dist(dist)
            return getattr(dreq, "url", None) != backend.expand_line(can.req.url)  # type: ignore[attr-defined]
        specifier = can.req.as_pinned_version(can.version).specifier
        assert specifier is not None
        return not specifier.contains(dist.version, prereleases=True)

    def compare_with_working_set(self) -> tuple[list[str], list[str], list[str]]:
        """Compares the candidates and return (to_add, to_update, to_remove)"""
        working_set = self.working_set
        candidates = self.candidates.copy()
        to_update: set[str] = set()
        to_remove: set[str] = set()

        for key, dist in working_set.items():
            if key == self.self_key:
                continue
            if key in candidates:
                can = candidates.pop(key)
                if self._should_update(dist, can):
                    to_update.add(key)
            elif (
                self.only_keep or self.clean and key not in self.all_candidate_keys
            ) and key not in self.SEQUENTIAL_PACKAGES:
                # Remove package only if it is not required by any group
                # Packages for packaging will never be removed
                to_remove.add(key)
        to_add = {
            strip_extras(name)[0]
            for name, _ in candidates.items()
            if name != self.self_key and strip_extras(name)[0] not in working_set
        }
        return (
            sorted(to_add),
            sorted(to_update),
            sorted(to_remove),
        )

    def install_candidate(self, key: str, progress: Progress) -> Candidate:
        """Install candidate"""
        can = self.candidates[key]
        job = progress.add_task(f"Installing {can.format()}...", total=1)
        try:
            self.manager.install(can)
        except Exception:
            progress.live.console.print(f"  [error]{termui.Emoji.FAIL}[/] Install {can.format()} failed")
            raise
        else:
            progress.live.console.print(f"  [success]{termui.Emoji.SUCC}[/] Install {can.format()} successful")
        finally:
            progress.update(job, completed=1, visible=False)
        return can

    def update_candidate(self, key: str, progress: Progress) -> tuple[Distribution, Candidate]:
        """Update candidate"""
        can = self.candidates[key]
        dist = self.working_set[strip_extras(key)[0]]
        dist_version = dist.version
        job = progress.add_task(
            f"Updating [req]{key}[/] [warning]{dist_version}[/] -> [warning]{can.version}[/]...",
            total=1,
        )
        try:
            self.manager.uninstall(dist)
            self.manager.install(can)
        except Exception:
            progress.live.console.print(
                f"  [error]{termui.Emoji.FAIL}[/] Update [req]{key}[/] "
                f"[warning]{dist_version}[/] "
                f"-> [warning]{can.version}[/] failed",
            )
            raise
        else:
            progress.live.console.print(
                f"  [success]{termui.Emoji.SUCC}[/] Update [req]{key}[/] "
                f"[warning]{dist_version}[/] "
                f"-> [warning]{can.version}[/] successful",
            )
        finally:
            progress.update(job, completed=1, visible=False)

        return dist, can

    def remove_distribution(self, key: str, progress: Progress) -> Distribution:
        """Remove distributions with given names."""
        dist = self.working_set[key]
        dist_version = dist.version

        job = progress.add_task(
            f"Removing [req]{key}[/] [warning]{dist_version}[/]...",
            total=1,
        )
        try:
            self.manager.uninstall(dist)
        except Exception:
            progress.live.console.print(
                f"  [error]{termui.Emoji.FAIL}[/] Remove [req]{key}[/] [warning]{dist_version}[/] failed",
            )
            raise
        else:
            progress.live.console.print(
                f"  [success]{termui.Emoji.SUCC}[/] Remove [req]{key}[/] [warning]{dist_version}[/] successful"
            )
        finally:
            progress.update(job, completed=1, visible=False)
        return dist

    def _show_headline(self, packages: dict[str, list[str]]) -> None:
        add, update, remove = packages["add"], packages["update"], packages["remove"]
        if not any((add, update, remove)):
            self.ui.echo("All packages are synced to date, nothing to do.")
            return
        results = ["[bold]Synchronizing working set with lock file[/]:"]
        results.extend(
            [
                f"[success]{len(add)}[/] to add,",
                f"[warning]{len(update)}[/] to update,",
                f"[error]{len(remove)}[/] to remove",
            ]
        )
        self.ui.echo(" ".join(results) + "\n")

    def _show_summary(self, packages: dict[str, list[str]]) -> None:
        to_add = [self.candidates[key] for key in packages["add"]]
        to_update = [(self.working_set[key], self.candidates[key]) for key in packages["update"]]
        to_remove = [self.working_set[key] for key in packages["remove"]]
        lines = []
        if to_add:
            lines.append("[bold]Packages to add[/]:")
            for can in to_add:
                lines.append(f"  - {can.format()}")
        if to_update:
            lines.append("[bold]Packages to update[/]:")
            for prev, cur in to_update:
                lines.append(f"  - [req]{cur.name}[/] [warning]{prev.version}[/] -> [warning]{cur.version}[/]")
        if to_remove:
            lines.append("[bold]Packages to remove[/]:")
            for dist in to_remove:
                lines.append(f"  - [req]{dist.metadata['Name']}[/] [warning]{dist.version}[/]")
        if lines:
            self.ui.echo("\n".join(lines))
        else:
            self.ui.echo("All packages are synced to date, nothing to do.")

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

        errors: list[str] = []
        failed_jobs: list[tuple[str, str]] = []

        def update_progress(future: Future | DummyFuture, kind: str, key: str) -> None:
            error = future.exception()
            if error:
                exc_info = (type(error), error, error.__traceback__)
                termui.logger.exception("Error occurs: ", exc_info=exc_info)
                failed_jobs.append((kind, key))
                errors.extend([f"{kind} [success]{key}[/] failed:\n", *traceback.format_exception(*exc_info)])

        # get rich progress and live handler to deal with multiple spinners
        with self.ui.logging("install"), self.ui.make_progress(
            " ",
            SpinnerColumn(termui.SPINNER, speed=1, style="primary"),
            "{task.description}",
        ) as progress:
            live = progress.live
            for kind, key in sequential_jobs:
                handlers[kind](key, progress)
            for i in range(self.retry_times + 1):
                with self.create_executor() as executor:
                    for kind, key in parallel_jobs:
                        future = executor.submit(handlers[kind], key, progress)
                        future.add_done_callback(functools.partial(update_progress, kind=kind, key=key))
                if not failed_jobs or i == self.retry_times:
                    break
                parallel_jobs, failed_jobs = failed_jobs, []
                errors.clear()
                live.console.print("Retry failed jobs")

            if errors:
                if self.ui.verbosity < termui.Verbosity.DETAIL:
                    live.console.print("\n[error]ERRORS[/]:")
                    live.console.print("".join(errors), end="")
                raise InstallationError("Some package operations are not complete yet")

            if self.install_self:
                self_key = self.self_key
                assert self_key and self.self_candidate
                self.candidates[self_key] = self.self_candidate
                word = "a" if self.no_editable else "an editable"
                live.console.print(f"Installing the project as {word} package...")
                if self_key in self.working_set:
                    self.update_candidate(self_key, progress)
                else:
                    self.install_candidate(self_key, progress)

            live.console.print(f"\n{termui.Emoji.POPPER} All complete!")
