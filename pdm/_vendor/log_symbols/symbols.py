# -*- coding: utf-8 -*-
"""Provide log symbols for various log levels."""
import codecs
import locale
import os
import sys

from enum import Enum
from pdm._vendor.colorama import init, deinit, Fore

init(autoreset=True)

_MAIN = {
    'info': 'ℹ',
    'success': '✔',
    'warning': '⚠',
    'error': '✖'
}

_FALLBACKS = {
    'info': '¡',
    'success': 'v',
    'warning': '!!',
    'error': '×'
}


def is_supported():
    """Check whether operating system supports main symbols or not.

    Returns
    -------
    boolean
        Whether operating system supports main symbols or not
    """
    if os.getenv("DISABLE_UNICODE_OUTPUT"):
        return False
    encoding = getattr(sys.stdout, "encoding")
    if encoding is None:
        encoding = locale.getpreferredencoding(False)

    try:
        encoding = codecs.lookup(encoding).name
    except Exception:
        encoding = "utf-8"
    return encoding == "utf-8"


_SYMBOLS = _MAIN if is_supported() else _FALLBACKS


class LogSymbols(Enum): # pylint: disable=too-few-public-methods
    """LogSymbol enum class.

    Attributes
    ----------
    ERROR : str
        Colored error symbol
    INFO : str
        Colored info symbol
    SUCCESS : str
        Colored success symbol
    WARNING : str
        Colored warning symbol
    """

    INFO = Fore.BLUE + _SYMBOLS['info'] + Fore.RESET
    SUCCESS = Fore.GREEN + _SYMBOLS['success'] + Fore.RESET
    WARNING = Fore.YELLOW + _SYMBOLS['warning'] + Fore.RESET
    ERROR = Fore.RED + _SYMBOLS['error'] + Fore.RESET

deinit()
