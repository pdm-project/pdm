# flake8: noqa
"""
This module provides a middle layer between pdm and pip.
All pip members are imported here for compatiblity purpose.
"""
from __future__ import annotations

import atexit
import inspect
import sys
from typing import TYPE_CHECKING, Optional, Tuple

from pip._internal.cache import WheelCache
from pip._internal.commands.install import InstallCommand as _InstallCommand
from pip._internal.index.package_finder import PackageFinder
from pip._internal.models.candidate import InstallationCandidate
from pip._internal.models.format_control import FormatControl
from pip._internal.models.link import Link
from pip._internal.models.target_python import TargetPython
from pip._internal.models.wheel import Wheel as PipWheel
from pip._internal.network.auth import MultiDomainBasicAuth
from pip._internal.network.cache import SafeFileCache
from pip._internal.network.download import Downloader
from pip._internal.operations.prepare import unpack_url
from pip._internal.req import InstallRequirement
from pip._internal.req.constructors import (
    install_req_from_editable,
    install_req_from_line,
    install_req_from_parsed_requirement,
)
from pip._internal.req.req_file import parse_requirements
from pip._internal.utils import logging as pip_logging
from pip._internal.utils.hashes import FAVORITE_HASH, STRONG_HASHES
from pip._internal.utils.temp_dir import global_tempdir_manager
from pip._internal.utils.urls import path_to_url, url_to_path
from pip._internal.vcs.versioncontrol import VcsSupport

try:
    from pip._internal.utils.compatibility_tags import get_supported
except ImportError:
    from pip._internal.pep425tags import get_supported

if TYPE_CHECKING:
    from optparse import Values


class InstallCommand(_InstallCommand):
    def __init__(self) -> None:
        super().__init__(name="InstallCommand", summary="Install packages.")


def get_abi_tag(python_version):
    # type: (Tuple[int, int]) -> Optional[str]
    """Return the ABI tag based on SOABI (if available) or emulate SOABI
    (CPython 2, PyPy).
    A replacement for pip._internal.models.pep425tags:get_abi_tag()
    """
    try:
        from wheel.pep425tags import get_abbr_impl, get_config_var
        from wheel.pep425tags import get_flag as _get_flag

        def get_flag(var, fallback, expected=True, warn=True):
            return _get_flag(
                var, fallback=lambda: fallback, expected=expected, warn=warn
            )

    except ModuleNotFoundError:
        from packaging.tags import interpreter_name as get_abbr_impl
        from wheel.bdist_wheel import get_config_var, get_flag

    soabi = get_config_var("SOABI")
    impl = get_abbr_impl()
    abi = None  # type: Optional[str]

    if not soabi and impl in {"cp", "pp"} and hasattr(sys, "maxunicode"):
        d = ""
        m = ""
        u = ""
        is_cpython = impl == "cp"
        if get_flag("Py_DEBUG", hasattr(sys, "gettotalrefcount"), warn=False):
            d = "d"
        if python_version < (3, 8) and get_flag(
            "WITH_PYMALLOC", is_cpython, warn=False
        ):
            m = "m"
        if python_version < (3, 3) and get_flag(
            "Py_UNICODE_SIZE",
            sys.maxunicode == 0x10FFFF,
            expected=4,
            warn=False,
        ):
            u = "u"
        abi = "%s%s%s%s%s" % (impl, "".join(map(str, python_version)), d, m, u)
    elif soabi and soabi.startswith("cpython-"):
        abi = "cp" + soabi.split("-")[1]
    elif soabi:
        abi = soabi.replace(".", "_").replace("-", "_")

    return abi


def get_package_finder(
    install_cmd: InstallCommand,
    options: Optional[Values] = None,
    python_version: Optional[Tuple[int, int]] = None,
    ignore_requires_python: Optional[bool] = None,
) -> PackageFinder:
    """Shim for compatibility to generate package finders.

    Build and return a :class:`~pip._internal.index.package_finder.PackageFinder`
    instance using the :class:`~pip._internal.commands.install.InstallCommand` helper
    method to construct the finder, shimmed with backports as needed for compatibility.
    """
    if options is None:
        options, _ = install_cmd.parser.parse_args([])
    session = install_cmd._build_session(options)
    atexit.register(session.close)
    build_kwargs = {"options": options, "session": session}
    if python_version:
        target_python_builder = TargetPython
        abi = get_abi_tag(python_version)
        builder_args = inspect.signature(target_python_builder).parameters
        target_python_params = {"py_version_info": python_version}
        if "abi" in builder_args:
            target_python_params["abi"] = abi
        elif "abis" in builder_args:
            target_python_params["abis"] = [abi]
        target_python = target_python_builder(**target_python_params)
        build_kwargs["target_python"] = target_python

    build_kwargs["ignore_requires_python"] = ignore_requires_python
    return install_cmd._build_package_finder(**build_kwargs)  # type: ignore
