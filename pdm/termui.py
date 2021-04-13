from __future__ import annotations

import atexit
import contextlib
import functools
import io
import logging
import os
import sys
from itertools import zip_longest
from tempfile import mktemp
from typing import Any, Callable, Iterator, List, Optional, Sequence, Union

import click
from click._compat import strip_ansi

from pdm._vendor import halo
from pdm._vendor.log_symbols.symbols import is_supported as supports_unicode

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.NullHandler())


def ljust(text: str, length: int) -> str:
    """Like str.ljust() but ignore all ANSI controlling characters."""
    return text + " " * (length - len(strip_ansi(text)))


def rjust(text: str, length: int) -> str:
    """Like str.rjust() but ignore all ANSI controlling characters."""
    return " " * (length - len(strip_ansi(text))) + text


def centerize(text: str, length: int) -> str:
    """Centerize the text while ignoring ANSI controlling characters."""
    space_num = length - len(strip_ansi(text))
    left_space = space_num // 2
    return " " * left_space + text + " " * (space_num - left_space)


def supports_ansi() -> bool:
    """Check if the current environment supports ANSI colors"""
    if os.getenv("CI"):
        return False
    stream = sys.stdout
    if not hasattr(stream, "fileno"):
        return False
    try:
        return os.isatty(stream.fileno())
    except io.UnsupportedOperation:
        return False


# Export some style shortcut helpers
green = functools.partial(click.style, fg="green")
red = functools.partial(click.style, fg="red")
yellow = functools.partial(click.style, fg="yellow")
cyan = functools.partial(click.style, fg="cyan")
blue = functools.partial(click.style, fg="blue")
bold = functools.partial(click.style, bold=True)

# Verbosity levels
NORMAL = 0
DETAIL = 1
DEBUG = 2


class DummySpinner:
    """A dummy spinner class implementing needed interfaces.
    But only display text onto screen.
    """

    def start(self, text: str) -> None:
        click.echo(text)

    succeed = fail = stop_and_persist = start

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

    def set_verbosity(self, verbosity: int) -> None:
        self.verbosity = verbosity

    def echo(
        self,
        message: str = "",
        err: bool = False,
        verbosity: int = NORMAL,
        **kwargs: Any,
    ) -> None:
        if self.verbosity >= verbosity:
            click.secho(
                self._indent + str(message), err=err, color=self.supports_ansi, **kwargs
            )

    def display_columns(
        self, rows: Sequence[Sequence[str]], header: Optional[List[str]] = None
    ) -> None:
        """Print rows in aligned columns.

        :param rows: a rows of data to be displayed.
        :param header: a list of header strings.
        """

        def get_aligner(align: str) -> Callable:
            if align == ">":
                return rjust
            if align == "^":
                return centerize
            else:
                return ljust

        sizes = list(
            map(
                lambda column: max(map(lambda x: len(strip_ansi(x)), column)),
                zip_longest(header or [], *rows, fillvalue=""),
            )
        )

        aligners = [ljust] * len(sizes)
        if header:
            aligners = []
            for i, head in enumerate(header):
                aligners.append(get_aligner(head[0]))
                if head[0] in (">", "^", "<"):
                    header[i] = head[1:]
            self.echo(
                " ".join(
                    aligner(head, size)
                    for aligner, head, size in zip(aligners, header, sizes)
                )
            )
            # Print a separator
            self.echo(" ".join("-" * size for size in sizes))
        for row in rows:
            self.echo(
                " ".join(
                    aligner(item, size)
                    for aligner, item, size in zip(aligners, row, sizes)
                )
            )

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
            handler = logging.StreamHandler()
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
                self.echo(yellow(f"See {file_name} for detailed debug log."))
            raise
        else:
            atexit.register(cleanup)
        finally:
            logger.handlers.remove(handler)
            pip_logger.handlers.remove(handler)

    def open_spinner(
        self, title: str, spinner: str = "dots"
    ) -> Union[DummySpinner, halo.Halo]:
        """Open a spinner as a context manager."""
        if self.verbosity >= DETAIL or not self.supports_ansi:
            return DummySpinner()
        else:
            return halo.Halo(  # type: ignore
                title, spinner=spinner, indent=self._indent
            )


class Emoji:
    """A collection of emoji characters used in terminal output"""

    if supports_unicode():  # type: ignore
        SUCC = "🎉"
        LOCK = "🔒"
    else:
        SUCC = ""
        LOCK = ""
