import functools
import re
from itertools import zip_longest
from typing import Any, List

import click

COLORS = ("red", "green", "yellow", "blue", "black", "magenta", "cyan", "white")

COLORS += tuple(f"bright_{color}" for color in COLORS)


@functools.lru_cache()
def _strip_styles(text):
    return re.sub(r"\x1b\[\d+?m", "", text)


def ljust(text, length):
    return text + " " * (length - len(_strip_styles(text)))


class _IO:
    NORMAL = 0
    DETAIL = 1
    DEBUG = 2

    def __init__(self, verbosity: int = NORMAL, disable_colors: bool = False) -> None:
        self.verbosity = verbosity
        self._disable_colors = disable_colors

        for color in COLORS:
            setattr(self, color, functools.partial(self._style, fg=color))

    def disable_colors(self) -> None:
        self._disable_colors = True

    def set_verbosity(self, verbosity: int) -> None:
        self.verbosity = verbosity

    def echo(
        self, message: Any = None, err: bool = False, verbosity: int = NORMAL, **kwargs
    ) -> None:
        if self.verbosity >= verbosity:
            click.echo(message, err=err, **kwargs)

    def _style(self, text: str, *args, **kwargs) -> str:
        if self._disable_colors:
            return text
        else:
            return click.style(text, *args, **kwargs)

    def display_columns(self, rows: List[str], header: List[str]) -> None:
        """Print rows in aligned columns"""
        sizes = list(
            map(
                lambda column: max(map(lambda x: len(_strip_styles(x)), column)),
                zip_longest(header, *rows),
            )
        )
        self.echo(" ".join(head.ljust(size) for head, size in zip(header, sizes)))
        # Print a separator
        self.echo(" ".join("-" * size for size in sizes))
        for row in rows:
            self.echo(" ".join(ljust(item, size) for item, size in zip(row, sizes)))
