import contextlib
import functools
import re
from itertools import zip_longest
from typing import List, Optional

import click

COLORS = ("red", "green", "yellow", "blue", "black", "magenta", "cyan", "white")

COLORS += tuple(f"bright_{color}" for color in COLORS)


@functools.lru_cache()
def _strip_styles(text):
    return re.sub(r"\x1b\[\d+?m", "", text)


def ljust(text, length):
    return text + " " * (length - len(_strip_styles(text)))


class IOStream:
    NORMAL = 0
    DETAIL = 1
    DEBUG = 2

    def __init__(self, verbosity: int = NORMAL, disable_colors: bool = False) -> None:
        self.verbosity = verbosity
        self._disable_colors = disable_colors
        self._indent = ""

        for color in COLORS:
            setattr(self, color, functools.partial(self._style, fg=color))

    def disable_colors(self) -> None:
        self._disable_colors = True

    def set_verbosity(self, verbosity: int) -> None:
        self.verbosity = verbosity

    def echo(
        self, message: str = "", err: bool = False, verbosity: int = NORMAL, **kwargs
    ) -> None:
        if self.verbosity >= verbosity:
            click.echo(self._indent + str(message), err=err, **kwargs)

    def _style(self, text: str, *args, **kwargs) -> str:
        if self._disable_colors:
            return text
        else:
            return click.style(text, *args, **kwargs)

    def display_columns(
        self, rows: List[str], header: Optional[List[str]] = None
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


stream = IOStream()
