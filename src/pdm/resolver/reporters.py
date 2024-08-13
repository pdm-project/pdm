from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Generator

from resolvelib import BaseReporter
from rich import get_console
from rich.live import Live
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TimeElapsedColumn

from pdm.models.reporter import CandidateReporter, RichProgressReporter
from pdm.termui import SPINNER, UI, Verbosity, logger

if TYPE_CHECKING:
    from resolvelib.resolvers import Criterion, RequirementInformation, State
    from rich.console import Console, ConsoleOptions, RenderResult

    from pdm.models.candidates import Candidate
    from pdm.models.requirements import Requirement


def log_title(title: str) -> None:
    logger.info("=" * 8 + " " + title + " " + "=" * 8)


class LockReporter(BaseReporter):
    @contextmanager
    def make_candidate_reporter(self, candidate: Candidate) -> Generator[CandidateReporter]:
        yield CandidateReporter()

    def starting(self) -> Any:
        log_title("Start resolving requirements")

    def adding_requirement(self, requirement: Requirement, parent: Candidate) -> None:
        parent_line = f"(from {parent.name} {parent.version})" if parent else ""
        logger.info("  Adding requirement %s%s", requirement.as_line(), parent_line)

    def ending(self, state: State) -> Any:
        log_title("Resolution Result")
        if state.mapping:
            column_width = max(map(len, state.mapping.keys()))
            for k, can in state.mapping.items():
                if not can.req.is_named:
                    can_info = can.req.url
                    if can.req.is_vcs:
                        can_info = f"{can_info}@{can.get_revision()}"
                else:
                    can_info = can.version
                logger.info(f"  {k.rjust(column_width)} {can_info}")


class RichLockReporter(LockReporter):
    def __init__(self, requirements: list[Requirement], ui: UI) -> None:
        self.ui = ui
        self.console = get_console()
        self.requirements = requirements
        self.progress = Progress(
            "[progress.description]{task.description}",
            "[info]{task.fields[text]}",
            BarColumn(),
            TaskProgressColumn(),
            console=self.console,
        )
        self._spinner = Progress(
            SpinnerColumn(SPINNER, style="primary"),
            TimeElapsedColumn(),
            "[bold]{task.description}",
            "{task.fields[info]}",
            console=self.console,
        )
        self._spinner_task = self._spinner.add_task("Resolving dependencies", info="", total=1)
        self.live = Live(self)

    @contextmanager
    def make_candidate_reporter(self, candidate: Candidate) -> Generator[CandidateReporter]:
        task_id = self.progress.add_task(f"Resolving {candidate.format()}", text="")
        try:
            yield RichProgressReporter(self.progress, task_id)
        finally:
            self.progress.update(task_id, visible=False)
            if candidate._prepared:
                candidate._prepared.reporter = CandidateReporter()

    def update(self, description: str | None = None, info: str | None = None, completed: float | None = None) -> None:
        self._spinner.update(self._spinner_task, description=description, info=info, completed=completed)
        self.live.refresh()

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:  # pragma: no cover
        yield self._spinner
        yield self.progress

    def start(self) -> None:
        """Start the progress display."""
        if self.ui.verbosity < Verbosity.DETAIL:
            self.live.start(refresh=True)

    def stop(self) -> None:
        """Stop the progress display."""
        self.live.stop()
        if not self.console.is_interactive:  # pragma: no cover
            self.console.print()

    def __enter__(self) -> RichLockReporter:
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.stop()

    def starting_round(self, index: int) -> None:
        log_title(f"Starting round {index}")

    def starting(self) -> None:
        """Called before the resolution actually starts."""
        log_title("Start resolving requirements")
        for req in self.requirements:
            logger.info("  " + req.as_line())

    def ending_round(self, index: int, state: State) -> None:
        """Called before each round of resolution ends.

        This is NOT called if the resolution ends at this round. Use `ending`
        if you want to report finalization. The index is zero-based.
        """
        resolved = len(state.mapping)
        to_resolve = len(state.criteria) - resolved
        self.update(info=f"[info]{resolved}[/] resolved, [info]{to_resolve}[/] to resolve")

    def rejecting_candidate(self, criterion: Criterion, candidate: Candidate) -> None:
        if not criterion.information:
            logger.info("Candidate rejected because it contains invalid metadata: %s", candidate)
            return
        *others, last = criterion.information
        logger.info(
            "Candidate rejected: %s because it introduces a new requirement %s"
            " that conflicts with other requirements:\n  %s",
            candidate,
            last.requirement.as_line(),  # type: ignore[attr-defined]
            "  \n".join(
                sorted({f"  {req.as_line()} (from {parent if parent else 'project'})" for req, parent in others})
            ),
        )

    def pinning(self, candidate: Candidate) -> None:
        """Called when adding a candidate to the potential solution."""
        logger.info("Adding new pin: %s %s", candidate.name, candidate.version)

    def resolving_conflicts(self, causes: list[RequirementInformation]) -> None:
        conflicts = sorted({f"  {req.as_line()} (from {parent if parent else 'project'})" for req, parent in causes})
        logger.info("Conflicts detected: \n%s", "\n".join(conflicts))
