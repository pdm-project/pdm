from __future__ import annotations

import dataclasses
import functools
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from functools import cached_property
from types import SimpleNamespace
from typing import TYPE_CHECKING, Collection

from rich.progress import SpinnerColumn, TaskProgressColumn

from pdm import termui
from pdm.environments import BaseEnvironment
from pdm.exceptions import BuildError, InstallationError
from pdm.installers.manager import InstallManager
from pdm.models.candidates import Candidate
from pdm.models.reporter import BaseReporter, RichProgressReporter
from pdm.models.requirements import FileRequirement, Requirement, parse_requirement, strip_extras
from pdm.utils import is_editable, normalize_name

if TYPE_CHECKING:
    from rich.progress import Progress

    from pdm.compat import Distribution


def editables_candidate(environment: BaseEnvironment) -> Candidate | None:
    """Return a candidate for `editables` package"""
    with environment.get_finder() as finder:
        best = finder.find_best_match("editables").best
    return None if best is None else Candidate.from_installation_candidate(best, parse_requirement("editables"))


class BaseSynchronizer:
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
    :param fail_fast: If true, stop the installation on first error
    """

    SEQUENTIAL_PACKAGES = ("pip", "setuptools", "wheel")

    def __init__(
        self,
        candidates: dict[str, Candidate],
        environment: BaseEnvironment,
        clean: bool = False,
        dry_run: bool = False,
        retry_times: int = 1,
        install_self: bool = False,
        no_editable: bool | Collection[str] = False,
        reinstall: bool = False,
        only_keep: bool = False,
        fail_fast: bool = False,
        use_install_cache: bool | None = None,
    ) -> None:
        self.requested_candidates = candidates
        self.environment = environment
        self.clean = clean
        self.dry_run = dry_run
        self.retry_times = retry_times
        self.no_editable = no_editable
        self.install_self = install_self
        if use_install_cache is None:
            use_install_cache = bool(environment.project.config["install.cache"])
        self.use_install_cache = use_install_cache
        self.reinstall = reinstall
        self.only_keep = only_keep
        self.parallel = environment.project.config["install.parallel"]
        self.fail_fast = fail_fast

        self.working_set = environment.get_working_set()
        self.ui = environment.project.core.ui
        self._manager: InstallManager | None = None

    @cached_property
    def self_candidate(self) -> Candidate:
        """Return the candidate for self project"""
        return self.environment.project.make_self_candidate(not self.no_editable)

    @cached_property
    def candidates(self) -> dict[str, Candidate]:
        """Return the candidates to be installed"""
        candidates = self.requested_candidates.copy()
        if isinstance(self.no_editable, Collection):
            keys = self.no_editable
        elif self.no_editable:
            keys = candidates.keys()
        else:
            keys = []
            if self.should_install_editables():
                # Install `editables` as well as required by self project
                editables = editables_candidate(self.environment)
                if editables is not None:
                    candidates["editables"] = editables
        for key in keys:
            if key in candidates and candidates[key].req.editable:
                candidate = candidates[key]
                # Create a new candidate with editable=False
                req = dataclasses.replace(candidate.req, editable=False)
                candidates[key] = candidate.copy_with(req)
        return candidates

    def should_install_editables(self) -> bool:
        """Return whether to add editables"""
        if not self.install_self or "editables" in self.requested_candidates:
            return False
        # As editables may be added by the backend, we need to check the metadata
        try:
            metadata = self.self_candidate.prepare(self.environment).metadata
        except BuildError:
            return False
        return any(req.startswith("editables") for req in metadata.requires or [])

    @property
    def manager(self) -> InstallManager:
        if not self._manager:
            self._manager = self.get_manager(rename_pth=True)
        return self._manager

    def get_manager(self, rename_pth: bool = False) -> InstallManager:
        return self.environment.project.core.install_manager_class(
            self.environment, use_install_cache=self.use_install_cache, rename_pth=rename_pth
        )

    @property
    def self_key(self) -> str | None:
        if not self.install_self:
            return None
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
            if not isinstance(dreq, FileRequirement):
                return True
            url = dreq.get_full_url()
            if dreq.is_local_dir:
                # We don't know whether a local dir has been changed, always update
                return True
            assert can.link is not None
            return url != backend.expand_line(can.link.url_without_fragment)
        specifier = can.req.as_pinned_version(can.version).specifier
        return not specifier.contains(dist.version, prereleases=True)

    def compare_with_working_set(self) -> tuple[list[str], list[str], list[str]]:
        """Compares the candidates and return (to_add, to_update, to_remove)"""
        working_set = self.working_set
        candidates = self.candidates.copy()
        to_update: set[str] = set()
        to_remove: set[str] = set()
        to_add: set[str] = set()
        locked_repository = self.environment.project.get_locked_repository()
        all_candidate_keys = list(locked_repository.all_candidates)

        for key, dist in working_set.items():
            if key == self.self_key and self.install_self:
                continue
            if key in candidates:
                can = candidates.pop(key)
                if self._should_update(dist, can):
                    if working_set.is_owned(key):
                        to_update.add(key)
                    else:
                        to_add.add(key)
            elif (
                (self.only_keep or self.clean and key not in all_candidate_keys)
                and key not in self.SEQUENTIAL_PACKAGES
                and working_set.is_owned(key)
            ):
                # Remove package only if it is not required by any group
                # Packages for packaging will never be removed
                to_remove.add(key)
        to_add.update(
            strip_extras(name)[0]
            for name, _ in candidates.items()
            if name != self.self_key and strip_extras(name)[0] not in working_set
        )
        return (sorted(to_add), sorted(to_update), sorted(to_remove))

    def synchronize(self) -> None:
        """Synchronize the working set with pinned candidates."""
        to_add, to_update, to_remove = self.compare_with_working_set()
        manager = self.get_manager()
        for key in to_add:
            can = self.candidates[key]
            termui.logger.info("Installing %s@%s...", key, can.version)
            manager.install(can)
        for key in to_update:
            can = self.candidates[key]
            dist = self.working_set[strip_extras(key)[0]]
            dist_version = dist.version
            termui.logger.info("Updating %s@%s -> %s...", key, dist_version, can.version)
            manager.uninstall(dist)
            manager.install(can)
        for key in to_remove:
            dist = self.working_set[key]
            termui.logger.info("Removing %s@%s...", key, dist.version)
            manager.uninstall(dist)
        termui.logger.info("Synchronization complete.")


class Synchronizer(BaseSynchronizer):
    def install_candidate(self, key: str, progress: Progress) -> Candidate:
        """Install candidate"""
        can = self.candidates[key]
        job = progress.add_task(f"Installing {can.format()}...", text="", total=None)
        can.prepare(self.environment, RichProgressReporter(progress, job))
        try:
            self.manager.install(can)
        except Exception:
            progress.live.console.print(f"  [error]{termui.Emoji.FAIL}[/] Install {can.format()} failed")
            raise
        else:
            progress.live.console.print(f"  [success]{termui.Emoji.SUCC}[/] Install {can.format()} successful")
        finally:
            progress.update(job, visible=False)
            can.prepare(self.environment, BaseReporter())
        return can

    def update_candidate(self, key: str, progress: Progress) -> tuple[Distribution, Candidate]:
        """Update candidate"""
        can = self.candidates[key]
        dist = self.working_set[strip_extras(key)[0]]
        dist_version = dist.version
        job = progress.add_task(
            f"Updating [req]{key}[/] [warning]{dist_version}[/] -> [warning]{can.version}[/]...", text="", total=None
        )
        can.prepare(self.environment, RichProgressReporter(progress, job))
        try:
            self.manager.overwrite(dist, can)
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
            progress.update(job, visible=False)
            can.prepare(self.environment, BaseReporter())

        return dist, can

    def remove_distribution(self, key: str, progress: Progress) -> Distribution:
        """Remove distributions with given names."""
        dist = self.working_set[key]
        dist_version = dist.version

        job = progress.add_task(f"Removing [req]{key}[/] [warning]{dist_version}[/]...", text="", total=None)
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
            progress.update(job, visible=False)
        return dist

    def _show_headline(self, packages: dict[str, list[str]]) -> None:
        add, update, remove = packages["add"], packages["update"], packages["remove"]
        if not any((add, update, remove)):
            self.ui.echo("All packages are synced to date, nothing to do.")
            return
        results = ["[bold]Synchronizing working set with resolved packages[/]:"]
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

    def _fix_pth_files(self) -> None:
        """Remove the .pdmtmp suffix from the installed packages"""
        from pathlib import Path

        lib_paths = self.environment.get_paths()
        for scheme in ["purelib", "platlib"]:
            for path in list(Path(lib_paths[scheme]).iterdir()):
                if path.suffix == ".pdmtmp":
                    target_path = path.with_suffix("")
                    if target_path.exists():
                        target_path.unlink()
                    path.rename(target_path)

    def synchronize(self) -> None:
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
                if key in self.SEQUENTIAL_PACKAGES or not self.parallel:
                    sequential_jobs.append((kind, key))
                elif key in self.candidates and self.candidates[key].req.editable:
                    # Editable packages are installed sequentially.
                    sequential_jobs.append((kind, key))
                else:
                    parallel_jobs.append((kind, key))

        state = SimpleNamespace(errors=[], parallel_failed=[], sequential_failed=[], jobs=[], mark_failed=False)

        def update_progress(future: Future, kind: str, key: str) -> None:
            error = future.exception()
            if error:
                exc_info = (type(error), error, error.__traceback__)
                termui.logger.exception("Error occurs: ", exc_info=exc_info)
                state.parallel_failed.append((kind, key))
                state.errors.extend([f"{kind} [success]{key}[/] failed:\n", *traceback.format_exception(*exc_info)])
                if self.fail_fast:
                    for future in state.jobs:
                        future.cancel()
                    state.mark_failed = True

        # get rich progress and live handler to deal with multiple spinners
        with self.ui.make_progress(
            " ",
            SpinnerColumn(termui.SPINNER, speed=1, style="primary"),
            "{task.description}",
            "[info]{task.fields[text]}",
            TaskProgressColumn("[info]{task.percentage:>3.0f}%[/]"),
        ) as progress:
            live = progress.live
            for i in range(self.retry_times + 1):
                for kind, key in sequential_jobs:
                    try:
                        handlers[kind](key, progress)
                    except Exception:
                        termui.logger.exception("Error occurs: ")
                        state.sequential_failed.append((kind, key))
                        state.errors.extend([f"{kind} [success]{key}[/] failed:\n", traceback.format_exc()])
                        if self.fail_fast:
                            state.mark_failed = True
                            break
                if state.mark_failed:
                    break
                state.jobs.clear()
                if parallel_jobs:
                    with ThreadPoolExecutor() as executor:
                        for kind, key in parallel_jobs:
                            future = executor.submit(handlers[kind], key, progress)
                            future.add_done_callback(functools.partial(update_progress, kind=kind, key=key))
                            state.jobs.append(future)
                if (
                    state.mark_failed
                    or i == self.retry_times
                    or not state.sequential_failed
                    and not state.parallel_failed
                ):
                    break
                sequential_jobs, state.sequential_failed = state.sequential_failed, []
                parallel_jobs, state.parallel_failed = state.parallel_failed, []
                state.errors.clear()
                live.console.print("Retry failed jobs")

            try:
                if state.errors:
                    if self.ui.verbosity < termui.Verbosity.DETAIL:
                        live.console.print("\n[error]ERRORS[/]:")
                        live.console.print("".join(state.errors), end="")
                    raise InstallationError("Some package operations are not complete yet")

                if self.install_self:
                    self_key = self.self_key
                    assert self_key
                    self.candidates[self_key] = self.self_candidate
                    word = "a" if self.no_editable else "an editable"
                    live.console.print(f"Installing the project as {word} package...")
                    if self_key in self.working_set:
                        self.update_candidate(self_key, progress)
                    else:
                        self.install_candidate(self_key, progress)

                live.console.print(f"\n{termui.Emoji.POPPER} All complete!")
            finally:
                # Now we remove the .pdmtmp suffix from the installed packages
                self._fix_pth_files()
