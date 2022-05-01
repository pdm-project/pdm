from __future__ import annotations

import atexit
import contextlib
import functools
import io
import logging
import os
import sys
from tempfile import mktemp
from typing import TYPE_CHECKING, Any, Iterator, List, Optional, Sequence, Type, Union

from rich.box import ROUNDED
from rich.console import Console
from rich.live import Live
from rich.progress import Progress, SpinnerColumn
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table
from rich.text import Text

from pdm._vendor import colorama
from pdm._vendor.log_symbols.symbols import is_supported as supports_unicode

if TYPE_CHECKING:
    from rich.status import Status


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.NullHandler())


def supports_ansi() -> bool:
    if os.getenv("CI") or not hasattr(sys.stdout, "fileno"):
        return False
    if sys.platform == "win32":
        return (
            os.getenv("ANSICON") is not None
            or os.getenv("WT_SESSION") is not None
            or "ON" == os.getenv("ConEmuANSI")
            or "xterm" == os.getenv("Term")
        )
    try:
        return os.isatty(sys.stdout.fileno())
    except io.UnsupportedOperation:
        return False


_console = Console(force_terminal=supports_ansi(), highlight=False)
_err_console = Console(force_terminal=supports_ansi(), stderr=True)


def style(
    text: str,
    *args: str,
    err: bool = False,
    style: str = None,
    bold: bool = False,
    **kwargs: Union[str, bool],
) -> str:
    # check for bold since mimicking click.secho
    if bold:
        style = f"{style} bold"

    console = _err_console if err else _console

    with console.capture() as capture:
        console.print(text, *args, end="", style=style, **kwargs)
    return capture.get()


# Export some style shortcut helpers
green = functools.partial(style, style="green")
red = functools.partial(style, style="red")
yellow = functools.partial(style, style="yellow")
cyan = functools.partial(style, style="cyan")
blue = functools.partial(style, style="blue")
bold = functools.partial(style, style="bold")


def confirm(*args: str, **kwargs: Any) -> str:
    return Confirm.ask(*args, **kwargs)


def ask(
    *args: str, prompt_type: Union[Type[str], Type[int]] = None, **kwargs: Any
) -> str:

    if not prompt_type or prompt_type == str:
        return Prompt.ask(*args, **kwargs)
    elif prompt_type == int:
        return str(IntPrompt.ask(*args, **kwargs))
    else:
        raise ValueError(f"unsupported {prompt_type}")


# Verbosity levels
NORMAL = 0
DETAIL = 1
DEBUG = 2


class DummySpinner:
    """A dummy spinner class implementing needed interfaces.
    But only display text onto screen.
    """

    def start(self, text: str) -> None:
        _console.print(text)

    def stop_and_persist(self, symbol: str = " ", text: Optional[str] = None) -> None:
        _console.print(symbol + " " + (text or ""))

    def update(self, text: str) -> None:
        self.text = text

    succeed = fail = start

    text = property(lambda self: "", start)

    def __enter__(self) -> DummySpinner:
        return self

    def __exit__(self, *args: Any) -> None:
        pass


class UI:
    """Terminal UI object"""

    def __init__(self, verbosity: int = NORMAL, no_ansi: Optional[bool] = None) -> None:
        self.verbosity = verbosity
        self._indent = ""
        self.supports_ansi = not no_ansi if no_ansi is not None else supports_ansi()
        if not self.supports_ansi:
            colorama.init()
        else:
            colorama.deinit()
        self._console = Console(force_terminal=self.supports_ansi)
        self._err_console = Console(force_terminal=self.supports_ansi, stderr=True)

    def set_verbosity(self, verbosity: int) -> None:
        self.verbosity = verbosity

    def echo(
        self,
        message: str = "",
        err: bool = False,
        verbosity: int = NORMAL,
        fg: str = None,
        **kwargs: Any,
    ) -> None:
        if self.verbosity >= verbosity:
            # TODO: Remove this once all termui.<color>
            # and termui.style calls are removed
            # try to catch text already formatted with ANSI
            if isinstance(message, str) and "[0m" in message:
                message = Text.from_ansi(self._indent + message)
            else:
                message = Text.from_markup(self._indent + str(message))

            console = _err_console if err else _console

            console.print(message, style=fg, **kwargs)

    def display_columns(
        self, rows: Sequence[Sequence[str]], header: Optional[List[str]] = None
    ) -> None:
        """Print rows in aligned columns.

        :param rows: a rows of data to be displayed.
        :param header: a list of header strings.
        """

        if header:
            table = Table(box=ROUNDED)
            for item in header:
                table.add_column(item)
        else:
            table = Table.grid(padding=(0, 1))
            for _ in rows[0]:
                table.add_column()
        for row in rows:
            table.add_row(*row)

        _console.print(table)

    @contextlib.contextmanager
    def indent(self, prefix: str) -> Iterator[None]:
        """Indent the following lines with a prefix."""
        _indent = self._indent
        self._indent += prefix
        yield
        self._indent = _indent

    @contextlib.contextmanager
    def logging(self, type_: str = "install") -> Iterator[logging.Logger]:
        """A context manager that opens a file for logging when verbosity is NORMAL or
        print to the stdout otherwise.
        """
        file_name = mktemp(".log", f"pdm-{type_}-")

        if self.verbosity >= DETAIL:
            handler: logging.Handler = logging.StreamHandler()
        else:
            handler = logging.FileHandler(file_name, encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        logger.handlers[1:] = [handler]
        pip_logger = logging.getLogger("pip.subprocessor")
        pip_logger.handlers[:] = [handler]

        def cleanup() -> None:
            try:
                os.unlink(file_name)
            except OSError:
                pass

        try:
            yield logger
        except Exception:
            if self.verbosity < DETAIL:
                logger.exception("Error occurs")
                self.echo(yellow(f"See {file_name} for detailed debug log."), err=True)
            raise
        else:
            atexit.register(cleanup)
        finally:
            logger.handlers.remove(handler)
            pip_logger.handlers.remove(handler)

    def open_spinner(
        self, title: str, spinner: str = "dots"
    ) -> Union[DummySpinner, Status]:
        """Open a spinner as a context manager."""
        if self.verbosity >= DETAIL or not self.supports_ansi:
            return DummySpinner()
        else:
            return self._console.status(
                title, spinner=spinner, spinner_style="bold cyan"
            )

    def live_progress(self, progress: Progress, console: Console = None) -> Live:
        return Live(
            progress,
            refresh_per_second=10,
            console=(console if console else self._console),
        )

    def make_progress(self) -> Progress:
        return Progress(
            " ",
            SpinnerColumn(speed=1, style="bold cyan"),
            "{task.description}",
        )


class Emoji:
    """A collection of emoji characters used in terminal output"""

    if supports_unicode():  # type: ignore
        SUCC = "🎉"
        LOCK = "🔒"
    else:
        SUCC = ""
        LOCK = ""
