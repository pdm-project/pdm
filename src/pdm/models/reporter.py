from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich import get_console
from rich.live import Live
from rich.progress import MofNCompleteColumn, Progress, SpinnerColumn, TaskProgressColumn, TimeElapsedColumn

from pdm import termui

if TYPE_CHECKING:
    from rich.console import Console, ConsoleOptions, RenderResult
    from rich.progress import Progress, TaskID


class CandidateReporter:
    def report_download(self, link: Any, completed: int, total: int | None) -> None:
        pass

    def report_build_start(self, filename: str) -> None:
        pass

    def report_build_end(self, filename: str) -> None:
        pass

    def report_unpack(self, filename: Path, completed: int, total: int | None) -> None:
        pass


@dataclass
class RichProgressReporter(CandidateReporter):
    progress: Progress
    task_id: TaskID

    def report_download(self, link: Any, completed: int, total: int | None) -> None:
        self.progress.update(self.task_id, completed=completed, total=total, text="Downloading...")

    def report_unpack(self, filename: Path, completed: int, total: int | None) -> None:
        self.progress.update(self.task_id, completed=completed, total=total, text="Unpacking...")

    def report_build_start(self, filename: str) -> None:
        task = self.progress._tasks[self.task_id]
        task.total = None
        task.finished_time = None
        self.progress.update(self.task_id, text="Building...")

    def report_build_end(self, filename: str) -> None:
        self.progress.update(self.task_id, text="")


class InstallationStatus:
    def __init__(self, ui: termui.UI, text: str) -> None:
        self.ui = ui
        self.console = get_console()
        self._spinner = Progress(
            SpinnerColumn(termui.SPINNER),
            TimeElapsedColumn(),
            "{task.description}",
            MofNCompleteColumn(),
            console=self.console,
        )
        self._spinner_task = self._spinner.add_task(text, total=None)
        self.progress = Progress(
            " ",
            SpinnerColumn(termui.SPINNER, style="primary"),
            "{task.description}",
            "[info]{task.fields[text]}",
            TaskProgressColumn("[info]{task.percentage:>3.0f}%[/]"),
            console=self.console,
        )
        self.live = Live(self, console=self.console)

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield self.progress
        yield ""
        yield self._spinner

    def update_spinner(
        self,
        *,
        total: float | None = None,
        completed: float | None = None,
        advance: float | None = None,
        description: str | None = None,
    ) -> None:
        if self.ui.verbosity >= termui.Verbosity.DETAIL and description is not None:
            self.console.print(f"  {description}")
        self._spinner.update(
            self._spinner_task, total=total, completed=completed, advance=advance, description=description
        )
        self.live.refresh()

    def start(self) -> None:
        """Start the progress display."""
        if self.ui.verbosity < termui.Verbosity.DETAIL:
            self.live.start(refresh=True)

    def stop(self) -> None:
        """Stop the progress display."""
        self.live.stop()
        if not self.console.is_interactive:
            self.console.print()

    def __enter__(self) -> InstallationStatus:
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.stop()
