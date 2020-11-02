"""
Source: https://stackoverflow.com/a/10455937/2692667
"""

import sys
import os

if os.name == "nt":
    import ctypes

    class _CursorInfo(ctypes.Structure):
        _fields_ = [("size", ctypes.c_int), ("visible", ctypes.c_byte)]


def hide(stream=sys.stdout):
    """Hide cursor.
    Parameters
    ----------
    stream: sys.stdout, Optional
        Defines stream to write output to.
    """
    if os.name == "nt":
        ci = _CursorInfo()
        handle = ctypes.windll.kernel32.GetStdHandle(-11)
        ctypes.windll.kernel32.GetConsoleCursorInfo(handle, ctypes.byref(ci))
        ci.visible = False
        ctypes.windll.kernel32.SetConsoleCursorInfo(handle, ctypes.byref(ci))
    elif os.name == "posix":
        stream.write("\033[?25l")
        stream.flush()


def show(stream=sys.stdout):
    """Show cursor.
    Parameters
    ----------
    stream: sys.stdout, Optional
        Defines stream to write output to.
    """
    if os.name == "nt":
        ci = _CursorInfo()
        handle = ctypes.windll.kernel32.GetStdHandle(-11)
        ctypes.windll.kernel32.GetConsoleCursorInfo(handle, ctypes.byref(ci))
        ci.visible = True
        ctypes.windll.kernel32.SetConsoleCursorInfo(handle, ctypes.byref(ci))
    elif os.name == "posix":
        stream.write("\033[?25h")
        stream.flush()
