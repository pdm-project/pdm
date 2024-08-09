from __future__ import annotations

import contextlib
import enum
import logging
import os
import tempfile
import warnings
from typing import TYPE_CHECKING

import rich
from rich.box import ROUNDED
from rich.console import Console
from rich.progress import Progress, ProgressColumn
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table
from rich.theme import Theme

from pdm.exceptions import PDMWarning

if TYPE_CHECKING:
    from typing import Any, Iterator, Sequence

    from pdm._types import RichProtocol, Spinner, SpinnerT

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.NullHandler())
unearth_logger = logging.getLogger("unearth")
unearth_logger.setLevel(logging.DEBUG)

DEFAULT_THEME = {
    "primary": "cyan",
    "success": "green",
    "warning": "yellow",
    "error": "red",
    "info": "blue",
    "req": "bold green",
}
rich.reconfigure(highlight=False, theme=Theme(DEFAULT_THEME))
_err_console = Console(stderr=True, theme=Theme(DEFAULT_THEME))


def is_interactive(console: Console | None = None) -> bool:
    """Check if the terminal is run under interactive mode"""
    if console is None:
        console = rich.get_console()
    return "PDM_NON_INTERACTIVE" not in os.environ and console.is_interactive


def is_legacy_windows(console: Console | None = None) -> bool:
    """Legacy Windows renderer may have problem rendering emojis"""
    if console is None:
        console = rich.get_console()
    return console.legacy_windows


def style(text: str, *args: str, style: str | None = None, **kwargs: Any) -> str:
    """return text with ansi codes using rich console

    :param text: message with rich markup, defaults to "".
    :param style: rich style to apply to whole string
    :return: string containing ansi codes
    """
    _console = rich.get_console()
    if _console.legacy_windows or not _console.is_terminal:  # pragma: no cover
        return text
    with _console.capture() as capture:
        _console.print(text, *args, end="", style=style, **kwargs)
    return capture.get()


def confirm(*args: str, **kwargs: Any) -> bool:
    default = kwargs.setdefault("default", False)
    if not is_interactive():
        return default
    return Confirm.ask(*args, **kwargs)


def ask(*args: str, prompt_type: type[str] | type[int] | None = None, **kwargs: Any) -> str:
    """prompt user and return response

    :prompt_type: which rich prompt to use, defaults to str.
    :raises ValueError: unsupported prompt type
    :return: str of user's selection
    """
    if not prompt_type or prompt_type is str:
        return Prompt.ask(*args, **kwargs)
    elif prompt_type is int:
        return str(IntPrompt.ask(*args, **kwargs))
    else:
        raise ValueError(f"unsupported {prompt_type}")


class Verbosity(enum.IntEnum):
    QUIET = -1
    NORMAL = 0
    DETAIL = 1
    DEBUG = 2


LOG_LEVELS = {
    Verbosity.NORMAL: logging.WARN,
    Verbosity.DETAIL: logging.INFO,
    Verbosity.DEBUG: logging.DEBUG,
}


class Emoji:
    if is_legacy_windows():
        SUCC = "v"
        FAIL = "x"
        LOCK = " "
        CONGRAT = " "
        POPPER = " "
        ELLIPSIS = "..."
        ARROW_SEPARATOR = ">"
    else:
        SUCC = ":heavy_check_mark:"
        FAIL = ":heavy_multiplication_x:"
        LOCK = ":lock:"
        POPPER = ":party_popper:"
        ELLIPSIS = "…"
        ARROW_SEPARATOR = "➤"


if is_legacy_windows():
    SPINNER = "line"
else:
    SPINNER = "dots"


class DummySpinner:
    """A dummy spinner class implementing needed interfaces.
    But only display text onto screen.
    """

    def __init__(self, text: str) -> None:
        self.text = text

    def _show(self) -> None:
        _err_console.print(f"[primary]STATUS:[/] {self.text}")

    def update(self, text: str) -> None:
        self.text = text
        self._show()

    def __enter__(self: SpinnerT) -> SpinnerT:
        self._show()  # type: ignore[attr-defined]
        return self

    def __exit__(self, *args: Any) -> None:
        pass


class SilentSpinner(DummySpinner):
    def _show(self) -> None:
        pass


class UI:
    """Terminal UI object"""

    def __init__(
        self, verbosity: Verbosity = Verbosity.NORMAL, *, exit_stack: contextlib.ExitStack | None = None
    ) -> None:
        self.verbosity = verbosity
        self.exit_stack = exit_stack or contextlib.ExitStack()
        self.log_dir: str | None = None

    def set_verbosity(self, verbosity: int) -> None:
        self.verbosity = Verbosity(verbosity)
        if self.verbosity == Verbosity.QUIET:
            self.exit_stack.enter_context(warnings.catch_warnings())
            warnings.simplefilter("ignore", PDMWarning, append=True)
            warnings.simplefilter("ignore", FutureWarning, append=True)

    def set_theme(self, theme: Theme) -> None:
        """set theme for rich console

        :param theme: dict of theme
        """
        rich.get_console().push_theme(theme)
        _err_console.push_theme(theme)

    def echo(
        self,
        message: str | RichProtocol = "",
        err: bool = False,
        verbosity: Verbosity = Verbosity.QUIET,
        **kwargs: Any,
    ) -> None:
        """print message using rich console

        :param message: message with rich markup, defaults to "".
        :param err: if true print to stderr, defaults to False.
        :param verbosity: verbosity level, defaults to QUIET.
        """
        if self.verbosity >= verbosity:
            console = _err_console if err else rich.get_console()
            if not console.is_interactive:
                kwargs.setdefault("crop", False)
                kwargs.setdefault("overflow", "ignore")
            console.print(message, **kwargs)

    def display_columns(self, rows: Sequence[Sequence[str]], header: list[str] | None = None) -> None:
        """Print rows in aligned columns.

        :param rows: a rows of data to be displayed.
        :param header: a list of header strings.
        """

        if header:
            table = Table(box=ROUNDED)
            for title in header:
                if title[0] == "^":
                    title, justify = title[1:], "center"
                elif title[0] == ">":
                    title, justify = title[1:], "right"
                else:
                    title, justify = title, "left"
                table.add_column(title, justify=justify)
        else:
            table = Table.grid(padding=(0, 1))
            for _ in rows[0]:
                table.add_column()
        for row in rows:
            table.add_row(*row)

        rich.print(table)

    @contextlib.contextmanager
    def logging(self, type_: str = "install") -> Iterator[logging.Logger]:
        """A context manager that opens a file for logging when verbosity is NORMAL or
        print to the stdout otherwise.
        """
        log_file: str | None = None
        if self.verbosity >= Verbosity.DETAIL:
            handler: logging.Handler = logging.StreamHandler()
            handler.setLevel(LOG_LEVELS[self.verbosity])
        else:
            if self.log_dir and not os.path.exists(self.log_dir):
                os.makedirs(self.log_dir, exist_ok=True)
            self._clean_logs()
            log_file = tempfile.mktemp(".log", f"pdm-{type_}-", self.log_dir)
            handler = logging.FileHandler(log_file, encoding="utf-8")
            handler.setLevel(logging.DEBUG)

        handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
        logger.addHandler(handler)
        unearth_logger.addHandler(handler)

        def cleanup() -> None:
            if not log_file:
                return
            with contextlib.suppress(OSError):
                os.unlink(log_file)

        try:
            yield logger
        except Exception:
            if self.verbosity < Verbosity.DETAIL:
                logger.exception("Error occurs")
                self.echo(
                    f"See [warning]{log_file}[/] for detailed debug log.",
                    style="error",
                    err=True,
                )
            raise
        else:
            self.exit_stack.callback(cleanup)
        finally:
            logger.removeHandler(handler)
            unearth_logger.removeHandler(handler)
            handler.close()

    def open_spinner(self, title: str) -> Spinner:
        """Open a spinner as a context manager."""
        if self.verbosity >= Verbosity.DETAIL or not is_interactive():
            return DummySpinner(title)
        else:
            return _err_console.status(title, spinner=SPINNER, spinner_style="primary")

    def make_progress(self, *columns: str | ProgressColumn, **kwargs: Any) -> Progress:
        """create a progress instance for indented spinners"""
        return Progress(*columns, disable=self.verbosity >= Verbosity.DETAIL, **kwargs)

    def info(self, message: str, verbosity: Verbosity = Verbosity.NORMAL) -> None:
        """Print a message to stdout."""
        self.echo(f"[info]INFO:[/] [dim]{message}[/]", err=True, verbosity=verbosity)

    def deprecated(self, message: str, verbosity: Verbosity = Verbosity.NORMAL) -> None:
        """Print a message to stdout."""
        self.echo(f"[warning]DEPRECATED:[/] [dim]{message}[/]", err=True, verbosity=verbosity)

    def warn(self, message: str, verbosity: Verbosity = Verbosity.NORMAL) -> None:
        """Print a message to stdout."""
        self.echo(f"[warning]WARNING:[/] {message}", err=True, verbosity=verbosity)

    def error(self, message: str, verbosity: Verbosity = Verbosity.QUIET) -> None:
        """Print a message to stdout."""
        self.echo(f"[error]ERROR:[/] {message}", err=True, verbosity=verbosity)

    def _clean_logs(self) -> None:
        import time
        from pathlib import Path

        if self.log_dir is None:
            return
        for file in Path(self.log_dir).iterdir():
            if not file.is_file():
                continue
            if file.stat().st_ctime < time.time() - 7 * 24 * 60 * 60:  # 7 days
                file.unlink()
