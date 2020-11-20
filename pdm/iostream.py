import contextlib
import functools
import io
import logging
import os
import re
import sys
from itertools import zip_longest
from tempfile import mktemp
from typing import List, Optional

import click

from pdm._vendor import halo
from pdm._vendor.log_symbols.symbols import is_supported as supports_unicode
from pdm.utils import cached_property

COLORS = ("red", "green", "yellow", "blue", "black", "magenta", "cyan", "white")

COLORS += tuple(f"bright_{color}" for color in COLORS)


@functools.lru_cache()
def _strip_styles(text):
    return re.sub(r"\x1b\[\d+?m", "", text)


def ljust(text, length):
    """Like str.ljust() but ignore all ANSI controlling characters."""
    return text + " " * (length - len(_strip_styles(text)))


class DummySpinner:
    """A dummy spinner class implementing needed interfaces.
    But only display text onto screen.
    """

    def start(self, text: str):
        stream.echo(text)

    succeed = fail = stop_and_persist = start

    text = property(lambda self: "", start)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class IOStream:
    NORMAL = 0
    DETAIL = 1
    DEBUG = 2

    def __init__(self, verbosity: int = NORMAL, disable_colors: bool = False) -> None:
        self.verbosity = verbosity
        self._indent = ""
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.DEBUG)
        logger.addHandler(logging.NullHandler())
        self.logger = logger

        for color in COLORS:
            setattr(self, color, functools.partial(self._style, fg=color))

    def set_verbosity(self, verbosity: int) -> None:
        self.verbosity = verbosity

    @cached_property
    def supports_ansi(self) -> bool:
        if os.getenv("CI"):
            return False
        stream = sys.stdout
        if not hasattr(stream, "fileno"):
            return False
        try:
            return os.isatty(stream.fileno())
        except io.UnsupportedOperation:
            return False

    def echo(
        self, message: str = "", err: bool = False, verbosity: int = NORMAL, **kwargs
    ) -> None:
        if self.verbosity >= verbosity:
            click.echo(self._indent + str(message), err=err, **kwargs)

    def _style(self, text: str, *args, **kwargs) -> str:
        if not self.supports_ansi:
            return text
        return click.style(text, *args, **kwargs)

    def bold(self, text: str, **kwargs) -> str:
        return self._style(text, bold=True, **kwargs)

    def display_columns(
        self, rows: List[List[str]], header: Optional[List[str]] = None
    ) -> None:
        """Print rows in aligned columns.

        :param rows: a rows of data to be displayed.
        :param header: a list of header strings.
        """
        sizes = list(
            map(
                lambda column: max(map(lambda x: len(_strip_styles(x)), column)),
                zip_longest(header or [], *rows, fillvalue=""),
            )
        )
        if header:
            self.echo(" ".join(head.ljust(size) for head, size in zip(header, sizes)))
            # Print a separator
            self.echo(" ".join("-" * size for size in sizes))
        for row in rows:
            self.echo(" ".join(ljust(item, size) for item, size in zip(row, sizes)))

    @contextlib.contextmanager
    def indent(self, prefix):
        """Indent the following lines with a prefix."""
        _indent = self._indent
        self._indent += prefix
        yield
        self._indent = _indent

    @contextlib.contextmanager
    def logging(self, type_: str = "install"):
        file_name = mktemp(".log", f"pdm-{type_}-")

        logger = self.logger
        if self.verbosity >= self.DETAIL:
            handler = logging.StreamHandler()
        else:
            handler = logging.FileHandler(file_name, encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        logger.handlers[1:] = [handler]
        pip_logger = logging.getLogger("pip.subprocessor")
        pip_logger.handlers[:] = [handler]
        try:
            yield logger
        except Exception:
            if self.verbosity < self.DETAIL:
                self.echo(self.yellow(f"See {file_name} for detailed debug log."))
            raise
        else:
            try:
                os.remove(file_name)
            except OSError:
                pass

    @contextlib.contextmanager
    def open_spinner(self, title: str, spinner: str = "dots"):
        if self.verbosity >= self.DETAIL or not self.supports_ansi:
            bar = DummySpinner()
        else:
            bar = halo.Halo(title, spinner=spinner, indent=self._indent)
        with bar as bar:
            yield bar


stream = IOStream()
if supports_unicode():
    CELE = "🎉"
    LOCK = "🔒"
else:
    CELE = ""
    LOCK = ""
