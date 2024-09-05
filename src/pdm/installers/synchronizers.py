from __future__ import annotations

import functools
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from types import SimpleNamespace
from typing import TYPE_CHECKING

from pdm import termui
from pdm.exceptions import InstallationError
from pdm.installers.base import BaseSynchronizer
from pdm.models.candidates import Candidate
from pdm.models.reporter import CandidateReporter, InstallationStatus, RichProgressReporter
from pdm.models.requirements import strip_extras

if TYPE_CHECKING:
    from rich.progress import Progress

    from pdm.compat import Distribution


class Synchronizer(BaseSynchronizer):
    def install_candidate(self, key: str, progress: Progress) -> Candidate:
        """Install candidate"""
        can = self.candidates[key]
        job = progress.add_task(f"Installing {can.format()}...", text="", total=None)
        can.prepare(self.environment, RichProgressReporter(progress, job))
        try:
            self.manager.install(can)
        except Exception:
            progress.console.print(f"  [error]{termui.Emoji.FAIL}[/] Install {can.format()} failed")
            raise
        else:
            progress.console.print(f"  [success]{termui.Emoji.SUCC}[/] Install {can.format()} successful")
        finally:
            progress.update(job, visible=False)
            can.prepare(self.environment, CandidateReporter())
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
            progress.console.print(
                f"  [error]{termui.Emoji.FAIL}[/] Update [req]{key}[/] "
                f"[warning]{dist_version}[/] "
                f"-> [warning]{can.version}[/] failed",
            )
            raise
        else:
            progress.console.print(
                f"  [success]{termui.Emoji.SUCC}[/] Update [req]{key}[/] "
                f"[warning]{dist_version}[/] "
                f"-> [warning]{can.version}[/] successful",
            )
        finally:
            progress.update(job, visible=False)
            can.prepare(self.environment, CandidateReporter())

        return dist, can

    def remove_distribution(self, key: str, progress: Progress) -> Distribution:
        """Remove distributions with given names."""
        dist = self.working_set[key]
        dist_version = dist.version

        job = progress.add_task(f"Removing [req]{key}[/] [warning]{dist_version}[/]...", text="", total=None)
        try:
            self.manager.uninstall(dist)
        except Exception:
            progress.console.print(
                f"  [error]{termui.Emoji.FAIL}[/] Remove [req]{key}[/] [warning]{dist_version}[/] failed",
            )
            raise
        else:
            progress.console.print(
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
            status.update_spinner(advance=1)  # type: ignore[has-type]
            if error:
                exc_info = (type(error), error, error.__traceback__)
                termui.logger.exception("Error occurs %sing %s: ", kind.rstrip("e"), key, exc_info=exc_info)
                state.parallel_failed.append((kind, key))
                state.errors.extend([f"{kind} [success]{key}[/] failed:\n", *traceback.format_exception(*exc_info)])
                if self.fail_fast:
                    for future in state.jobs:
                        future.cancel()
                    state.mark_failed = True

        # get rich progress and live handler to deal with multiple spinners
        with InstallationStatus(self.ui, "Synchronizing") as status:
            for i in range(self.retry_times + 1):
                status.update_spinner(completed=0, total=len(sequential_jobs) + len(parallel_jobs))
                for kind, key in sequential_jobs:
                    try:
                        handlers[kind](key, status.progress)
                    except Exception:
                        termui.logger.exception("Error occurs: ")
                        state.sequential_failed.append((kind, key))
                        state.errors.extend([f"{kind} [success]{key}[/] failed:\n", traceback.format_exc()])
                        if self.fail_fast:
                            state.mark_failed = True
                            break
                    finally:
                        status.update_spinner(advance=1)
                if state.mark_failed:
                    break
                state.jobs.clear()
                if parallel_jobs:
                    with ThreadPoolExecutor() as executor:
                        for kind, key in parallel_jobs:
                            future = executor.submit(handlers[kind], key, status.progress)
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
                status.update_spinner(description=f"Retry failed jobs({i + 2}/{self.retry_times + 1})")

            try:
                if state.errors:
                    if self.ui.verbosity < termui.Verbosity.DETAIL:
                        status.console.print("\n[error]ERRORS[/]:")
                        status.console.print("".join(state.errors), end="")
                    status.update_spinner(description=f"[error]{termui.Emoji.FAIL}[/] Some package operations failed.")
                    raise InstallationError("Some package operations failed.")

                if self.install_self:
                    self_key = self.self_key
                    assert self_key
                    self.candidates[self_key] = self.self_candidate
                    word = "a" if self.no_editable else "an editable"
                    status.update_spinner(description=f"Installing the project as {word} package...")
                    if self_key in self.working_set:
                        self.update_candidate(self_key, status.progress)
                    else:
                        self.install_candidate(self_key, status.progress)

                status.update_spinner(description=f"{termui.Emoji.POPPER} All complete!")
            finally:
                # Now we remove the .pdmtmp suffix from the installed packages
                self._fix_pth_files()
